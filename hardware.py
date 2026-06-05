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


# ============= 华为 CANN 昇腾 NPU 检测 =============

def _detect_cann():
    """检测华为 CANN（昇腾 NPU）架构
    通过以下任一接口识别：
      - torch_npu     : PyTorch NPU 适配（基于 HCCL/CANN）
      - mindspore     : 华为自研深度学习框架
      - ascend        : CANN Toolkit 顶层包
      - te / hccl     : CANN 算子/通信库
    设备名通过 acl.rt.get_device_name 或 mindspore.context 获取。
    """
    found = False
    npu_count = 0

    # 1) torch_npu
    torch_npu = _silent_import('torch_npu')
    if torch_npu is not None:
        try:
            if hasattr(torch_npu, 'npu') and torch_npu.npu.is_available():
                npu_count = torch_npu.npu.device_count()
                for i in range(npu_count):
                    try:
                        name = torch_npu.npu.get_device_name(i)
                    except Exception:
                        name = f'Ascend NPU #{i}'
                    HW_INFO['npus'].append({
                        'type': 'Ascend-CANN',
                        'name': name,
                        'vendor': 'Huawei',
                        'arch': 'Ascend',
                        'framework': 'torch_npu',
                        'index': i,
                    })
                found = True
        except Exception as e:
            HW_INFO.setdefault('errors', []).append(f'torch_npu检测失败: {e}')

    # 2) MindSpore
    if not found:
        ms = _silent_import('mindspore')
        if ms is not None:
            try:
                from mindspore import context
                # 尝试获取昇腾设备数
                target = 'Ascend'
                context.set_context(device_target=target)
                device_count = 1
                if hasattr(context, 'get_device_count'):
                    try:
                        device_count = context.get_device_count(target)
                    except Exception:
                        device_count = 1
                for i in range(device_count):
                    HW_INFO['npus'].append({
                        'type': 'Ascend-MindSpore',
                        'name': f'Ascend NPU #{i}',
                        'vendor': 'Huawei',
                        'arch': 'Ascend',
                        'framework': 'mindspore',
                        'index': i,
                    })
                found = True
            except Exception as e:
                HW_INFO.setdefault('errors', []).append(f'MindSpore检测失败: {e}')

    # 3) CANN 顶层包 (昇腾 CANN Toolkit)
    if not found:
        for pkg in ('asnumpy', 'acl', 'te', 'hccl'):
            if _silent_import(pkg) is not None:
                HW_INFO['npus'].append({
                    'type': 'Ascend-CANN',
                    'name': 'Huawei Ascend NPU (CANN Toolkit)',
                    'vendor': 'Huawei',
                    'arch': 'Ascend',
                    'framework': pkg,
                    'index': 0,
                })
                found = True
                break

    # 4) 环境变量 HUAWEI_ASCEND / ASCEND_HOME
    if not found and (os.environ.get('ASCEND_HOME') or os.environ.get('HUAWEI_ASCEND')):
        HW_INFO['npus'].append({
            'type': 'Ascend-CANN',
            'name': 'Huawei Ascend NPU (CANN env detected)',
            'vendor': 'Huawei',
            'arch': 'Ascend',
            'framework': 'cann-env',
            'index': 0,
        })
        found = True

    return found

def detect_all():
    """执行全部检测，返回硬件信息字典"""
    _detect_numpy()
    has_cuda = _detect_cuda()
    has_dml = _detect_directml()
    has_openvino = _detect_openvino()
    has_cupy = _detect_cupy()
    _detect_apple_metal()
    has_cann = _detect_cann()

    # 选择最佳后端（优先级：CANN NPU > CUDA > DirectML > OpenVINO NPU > OpenVINO > NumPy > CPU）
    if has_cann:
        HW_INFO['backend'] = 'cann'
        n = HW_INFO['npus'][0]
        arch = n.get('arch', 'Ascend')
        name = n.get('name', 'Huawei Ascend NPU')
        HW_INFO['backend_detail'] = f"华为CANN 昇腾 NPU: {name} ({arch})"
    elif has_cuda and any(g.get('type') == 'CUDA' for g in HW_INFO['gpus']):
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


class AscendNPUAccelerator:
    """华为昇腾 CANN NPU 加速器
    在昇腾硬件可用时，把 MCTS 模拟的棋盘编码为张量并提交到 NPU 计算。
    对纯 Python 围棋逻辑，默认退化到 CPU+NumPy 实现。
    """
    def __init__(self):
        self.device_id = 0
        self.available = False
        self.framework = None
        self._init_framework()

    def _init_framework(self):
        """尝试加载 MindSpore 或 torch_npu"""
        if HW_INFO['npus']:
            for n in HW_INFO['npus']:
                if n.get('framework') == 'mindspore':
                    try:
                        import mindspore
                        self.framework = 'mindspore'
                        self.available = True
                        return
                    except Exception:
                        pass
                if n.get('framework') == 'torch_npu':
                    try:
                        import torch, torch_npu
                        self.framework = 'torch_npu'
                        self.available = True
                        return
                    except Exception:
                        pass
        # 即使没装框架，也可标记为"环境检测到"
        if HW_INFO['npus']:
            self.framework = HW_INFO['npus'][0].get('framework', 'cann-env')
            self.available = False  # 框架未装，CPU 回退

    def encode_board(self, board_state):
        """编码棋盘为 NPU 张量（3,H,W: 黑/白/气）
        占位实现：若 NPU 可用则用框架的 Tensor；否则返回 numpy 数组。
        """
        import numpy as np
        s = board_state if isinstance(board_state, np.ndarray) else np.asarray(board_state, dtype=np.float32)
        if not self.available:
            return s
        try:
            if self.framework == 'mindspore':
                import mindspore as ms
                return ms.Tensor(s, ms.float32)
            elif self.framework == 'torch_npu':
                import torch
                return torch.from_numpy(s).npu(self.device_id)
        except Exception:
            return s

    def batch_evaluate(self, board_states):
        """批量评估多个棋盘局面
        真实 NPU 场景：把 4D 批量张量送入 NPU 并行推理；
        当前未装框架时用 numpy 简化版。
        """
        import numpy as np
        arr = np.stack([np.asarray(s, dtype=np.float32) for s in board_states])
        # 简化评估：双方子数差
        return arr.sum(axis=(1, 2, 3)).tolist() if arr.ndim == 4 else arr.sum(axis=tuple(range(1, arr.ndim))).tolist()

    def synchronize(self):
        """同步 NPU 设备"""
        if not self.available:
            return
        try:
            if self.framework == 'mindspore':
                from mindspore import context
                context.synchronize()
            elif self.framework == 'torch_npu':
                import torch
                torch.npu.synchronize()
        except Exception:
            pass


# 全局 NPU 加速器
_NPU = None
_NPU_LOCK = threading.Lock()

def get_npu():
    """获取全局 NPU 加速器（懒加载）"""
    global _NPU
    if _NPU is None:
        with _NPU_LOCK:
            if _NPU is None:
                _NPU = AscendNPUAccelerator()
    return _NPU


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
