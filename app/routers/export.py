from fastapi import APIRouter,Depends,Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.db import get_db
router=APIRouter(prefix="/api/export",tags=["export"])
def filters(notion_sync_status,category_level_1,platform,keyword,limit,include_raw_content=False):return locals()
@router.get("/json")
def export_json(request:Request,notion_sync_status:str|None=None,category_level_1:str|None=None,platform:str|None=None,keyword:str|None=None,limit:int=100,include_raw_content:bool=False,db:Session=Depends(get_db)):
 try:data=request.app.state.container.export_service.export_items_as_json(db,filters(notion_sync_status,category_level_1,platform,keyword,limit,include_raw_content));return {"success":True,"message":"导出成功","data":data}
 except (ValueError,KeyError) as exc:return JSONResponse(422,{"success":False,"message":str(exc),"data":None})
@router.get("/markdown")
def export_markdown(request:Request,notion_sync_status:str|None=None,category_level_1:str|None=None,platform:str|None=None,keyword:str|None=None,limit:int=100,db:Session=Depends(get_db)):
 try:content=request.app.state.container.export_service.export_items_as_markdown(db,filters(notion_sync_status,category_level_1,platform,keyword,limit));return {"success":True,"message":"导出成功","data":{"format":"markdown","content":content}}
 except (ValueError,KeyError) as exc:return JSONResponse(422,{"success":False,"message":str(exc),"data":None})
