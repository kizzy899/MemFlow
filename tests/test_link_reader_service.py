import sys
from types import SimpleNamespace
from app.config import Settings
from app.services.link_reader_service import LinkReaderService


class Parser: pass


def test_github_repo_detection_and_source_types():
    service=LinkReaderService(Settings(), Parser())
    assert service._github_repo("https://github.com/openai/codex") == ("openai", "codex")
    assert service._github_repo("https://github.com/openai/codex/issues") is None
    assert service._infer_source_type("https://youtu.be/x") == "视频笔记"


def test_pdf_reader_extracts_text(monkeypatch):
    class Response:
        content=b"pdf"
        def raise_for_status(self): pass
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def get(self,*args,**kwargs): return Response()
    class Page:
        def extract_text(self): return "PDF 正文"
    class Reader:
        pages=[Page()]; metadata={"/Title":"PDF 标题"}
        def __init__(self, stream): pass
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=Reader))
    service=LinkReaderService(Settings(), Parser()); monkeypatch.setattr(service, "_client", lambda: Client())
    result=service.read("https://example.com/file.pdf")
    assert result.source_type == "PDF" and result.content == "PDF 正文"