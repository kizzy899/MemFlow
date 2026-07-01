import time
import pytest
from app.services.processor_manager import ProcessorManager


class Archive:
    def run(self, db, progress=None):
        progress("processing",{"current_url":"https://example.com"})
        progress("result",{"status":"processed","message":"ok"})
        return {"results":[{"status":"processed","message":"ok"}],"processed":1,"skipped_duplicate":0,"failed_fetch":0,"failed_parse":0,"failed_notion":0}


def test_processor_manager_reports_progress(monkeypatch):
    class Context:
        def __enter__(self): return object()
        def __exit__(self,*args): pass
    monkeypatch.setattr("app.services.processor_manager.SessionLocal",lambda:Context())
    manager=ProcessorManager(Archive()); started=manager.start()
    assert started["status"]=="processing"
    with pytest.raises(RuntimeError): manager.start()
    for _ in range(100):
        state=manager.status()
        if state["status"]!="processing": break
        time.sleep(.01)
    assert state["status"]=="success" and state["success"]==1 and state["processed"]==1