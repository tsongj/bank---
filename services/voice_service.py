"""语音播报：模拟银行到账/扣款提示音。

用独立的守护线程 + 队列串行播报，避免 pyttsx3 在多线程下冲突；
语音引擎不可用时静默降级，绝不影响记账主流程。
"""
import queue
import threading

import config

_queue: "queue.Queue[str]" = queue.Queue()
_started = False
_start_lock = threading.Lock()


def _worker():
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", config.VOICE_RATE)
    except Exception:
        return  # 引擎不可用，直接退出工作线程，后续播报全部丢弃

    while True:
        text = _queue.get()
        if text is None:
            return
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
        finally:
            _queue.task_done()


def _ensure_worker():
    global _started
    if _started:
        return
    with _start_lock:
        if not _started:
            threading.Thread(target=_worker, daemon=True).start()
            _started = True


def speak(text: str):
    """播报任意文本。"""
    if not config.VOICE_ENABLED or not text:
        return
    try:
        _ensure_worker()
        _queue.put(text)
    except Exception:
        pass


def announce(amount: float, reason: str = ""):
    """按交易金额自动生成银行式播报。"""
    value = f"{round(abs(amount), 2):g}"
    if amount >= 0:
        speak(f"成长银行到账 {value} {config.CURRENCY_SYMBOL}")
    else:
        speak(f"成长银行扣除 {value} {config.CURRENCY_SYMBOL}")
