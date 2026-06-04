"""硬件自动检测与优化模块
按优先级检测可用加速后端：
  1. CUDA (PyTorch)        - NVIDIA GPU
  2. DirectML              - Windows GPU (AMD/Intel/NVIDIA)
  3. OpenVINO              - Intel NPU/GPU/CPU
  4. NumPy SIMD + 多线程   - 纯 CPU 向量化
  5. 纯 Python             - 兜底
"""
import os
import sys
import time
import platform
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import json

# 硬件信息
HW_INFO = {
    'os': platform.platform(),
    'arch': platform.machine(),
    'cpu': platform.processor() or platform.machine(),
    'cores': multiprocessing.cpu_count(),
    'gpus': [],
    'npus': [],
    'backend': 'cpu',
    'backend_detail': '',
    'simd': False,
    'numpy': None,
}

def _detect_numpy():
    """检测 NumPy 及 SIMD 加速"""
    try:
        import numpy as np
        HW_INFO['numpy'] = np.__version__
        HW_INFO['simd'] = True  # 假设已启用
        return True
    except ImportError:
        return False

def _silent_import(modname):
    """静默导入模块（抑制 ImportError 等噪声）"""
    import importlib, contextlib, io, sys
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return importlib.import_module(modname)
    except Exception:
        return None

def _detect_cuda():
    """检测 NVIDIA CUDA GPU（通过 PyTorch）"""
    torch = _silent_import('torch')
    if torch is None:
        return False
    try:
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                cap = torch.cuda.get_device_capability(i)
                mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                HW_INFO['gpus'].append({
                    'type': 'CUDA',
                    'name': name,
                    'capability': f'{cap[0]}.{cap[1]}',
                    'memory_gb': round(mem, 2),
                    'index': i,
                })
            return True
    except Exception as e:
        HW_INFO.setdefault('errors', []).append(f'CUDA检测失败: {e}')
    return False

def _detect_directml():
    """检测 DirectML（Windows GPU 加速，AMD/Intel/NVIDIA通用）"""
    ort = _silent_import('onnxruntime')
    if ort is None:
        return False
    try:
        providers = ort.get_available_providers()
        if 'DmlExecutionProvider' in providers:
            HW_INFO['gpus'].append({
                'type': 'DirectML',
                'name': 'Windows GPU (DirectML)',
                'provider': 'DmlExecutionProvider',
            })
            return True
    except Exception as e:
        HW_INFO.setdefault('errors', []).append(f'DirectML检测失败: {e}')
    return False

def _detect_openvino():
    """检测 OpenVINO（Intel NPU/GPU/VPU）"""
    ov = _silent_import('openvino.runtime')
    if ov is None:
        return False
    try:
        Core = ov.Core
        core = Core()
        devices = core.available_devices
        for d in devices:
            try:
                name = core.get_property(d, 'FULL_DEVICE_NAME')
            except Exception:
                name = d
            if 'NPU' in d.upper() or 'NPU' in str(name).upper() or 'VPU' in d.upper():
                HW_INFO['npus'].append({
                    'type': 'OpenVINO-NPU',
                    'device': d,
                    'name': name,
                })
            else:
                HW_INFO['gpus'].append({
                    'type': 'OpenVINO',
                    'device': d,
                    'name': name,
                })
        if HW_INFO['npus'] or HW_INFO['gpus']:
            return True
    except Exception as e:
        HW_INFO.setdefault('errors', []).append(f'OpenVINO检测失败: {e}')
    return False

def _detect_cupy():
    """检测 CuPy（轻量级CUDA加速）"""
    cupy = _silent_import('cupy')
    if cupy is None:
        return False
    try:
        n = cupy.cuda.runtime.getDeviceCount()
        for i in range(n):
            props = cupy.cuda.runtime.getDeviceProperties(i)
            HW_INFO['gpus'].append({
                'type': 'CuPy-CUDA',
                'name': props['name'].decode() if isinstance(props['name'], bytes) else str(props['name']),
                'memory_gb': round(props['totalGlobalMem'] / (1024**3), 2),
                'index': i,
            })
        return True
    except Exception:
        return False

def _detect_apple_metal():
    """检测 Apple Metal"""
    if sys.platform != 'darwin':
        return False
    try:
        torch = _silent_import('torch')
        if torch and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            HW_INFO['gpus'].append({
                'type': 'Apple-Metal',
                'name': 'Apple Silicon GPU',
            })
            return True
    except Exception:
        pass
    return False

def detect_all():
    """执行全部检测，返回硬件信息字典"""
    _detect_numpy()
    has_cuda = _detect_cuda()
    has_dml = _detect_directml()
    has_openvino = _detect_openvino()
    has_cupy = _detect_cupy()
    _detect_apple_metal()

    # 选择最佳后端
    if has_cuda and any(g.get('type') == 'CUDA' for g in HW_INFO['gpus']):
        HW_INFO['backend'] = 'cuda'
        g = next(g for g in HW_INFO['gpus'] if g['type'] == 'CUDA')
        HW_INFO['backend_detail'] = f"CUDA GPU: {g['name']} ({g.get('memory_gb', '?')}GB)"
    elif has_dml:
        HW_INFO['backend'] = 'directml'
        HW_INFO['backend_detail'] = 'DirectML GPU加速'
    elif has_openvino and HW_INFO['npus']:
        HW_INFO['backend'] = 'npu'
        n = HW_INFO['npus'][0]
        HW_INFO['backend_detail'] = f"Intel NPU: {n['name']}"
    elif has_openvino and HW_INFO['gpus']:
        HW_INFO['backend'] = 'openvino'
        g = next((x for x in HW_INFO['gpus'] if x['type'] == 'OpenVINO'), None)
        HW_INFO['backend_detail'] = f"OpenVINO: {g['name']}" if g else 'OpenVINO'
    elif HW_INFO['numpy']:
        HW_INFO['backend'] = 'numpy-simd'
        HW_INFO['backend_detail'] = f"NumPy {HW_INFO['numpy']} + SIMD, {HW_INFO['cores']}核"
    else:
        HW_INFO['backend'] = 'cpu'
        HW_INFO['backend_detail'] = f"纯Python, {HW_INFO['cores']}核"

    return HW_INFO


# ============= 优化工具 =============

class ParallelSimulator:
    """并行模拟器：使用线程池加速 MCTS 模拟
    Python GIL 限制下，对纯 Python 任务线程池仍能并行 I/O 和 numpy 操作。
    对 CPU 密集型，可选 ProcessPoolExecutor。
    """
    def __init__(self, max_workers=None, use_process=False):
        self.max_workers = max_workers or min(8, HW_INFO['cores'])
        self.use_process = use_process
        if use_process:
            self._pool = ProcessPoolExecutor(max_workers=self.max_workers)
        else:
            self._pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self._stats = {'sims': 0, 'time': 0.0}

    def map(self, fn, items):
        """并行映射"""
        start = time.time()
        results = list(self._pool.map(fn, items))
        self._stats['sims'] += len(items)
        self._stats['time'] += time.time() - start
        return results

    def shutdown(self):
        self._pool.shutdown(wait=False)

    def stats(self):
        return dict(self._stats)


# 全局并行模拟器（懒加载）
_PARALLEL = None
_PARALLEL_LOCK = threading.Lock()

def get_parallel():
    global _PARALLEL
    if _PARALLEL is None:
        with _PARALLEL_LOCK:
            if _PARALLEL is None:
                _PARALLEL = ParallelSimulator()
    return _PARALLEL


def numpy_batch_eval(scores_list):
    """使用 NumPy 批量评估一组棋局局面（向量化加速）
    每个局面被编码为 (3, size, size) 特征平面（黑子/白子/气），
    演示用：返回每个局面的简单启发式分数。
    """
    if not HW_INFO.get('numpy'):
        return [s for s in scores_list]
    try:
        import numpy as np
        arr = np.array(scores_list, dtype=np.float32)
        # 向量化：每位玩家控制区域近似 = 自身石子数 - 对手石子数
        # 这里做一个简单的和
        return arr.sum(axis=tuple(range(1, arr.ndim))).tolist()
    except Exception:
        return [sum(np.sum(np.asarray(s, dtype=np.float32)) for s in scores_list)]


def set_thread_env():
    """根据硬件设置 OpenMP/MKL 线程数"""
    cores = HW_INFO['cores']
    # 限制线程库使用物理核心数
    os.environ.setdefault('OMP_NUM_THREADS', str(max(1, cores - 1)))
    os.environ.setdefault('MKL_NUM_THREADS', str(max(1, cores - 1)))
    os.environ.setdefault('OPENBLAS_NUM_THREADS', str(max(1, cores - 1)))
    os.environ.setdefault('NUMEXPR_NUM_THREADS', str(max(1, cores - 1)))
    # TensorFlow 静默
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')


def get_info():
    """返回当前硬件信息"""
    return dict(HW_INFO)


def get_backend():
    """返回当前选定的后端"""
    return HW_INFO['backend']


# 启动时自动检测
if __name__ == '__main__':
    detect_all()
    set_thread_env()
    print(json.dumps(HW_INFO, ensure_ascii=False, indent=2))
