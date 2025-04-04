from fastapi import APIRouter, HTTPException
from domain.services.module_service import ModuleService
from api.schemas.requests import CreateModuleRequest, FetchModulesRequest
from api.schemas.responses import CreateModuleResponse, FetchModulesResponse, ModuleData

router = APIRouter()


class ModuleController:

    def __init__(self):
        self.service = ModuleService()

    async def create_module(
            self, request: CreateModuleRequest) -> CreateModuleResponse:
        if not request.user_id:
            raise HTTPException(status_code=400, detail="Missing 'userId'")
        if not request.module_name:
            raise HTTPException(status_code=400, detail="Missing 'moduleName'")
        if not request.simulations:
            raise HTTPException(status_code=400,
                                detail="Missing 'simulations'")

        result = await self.service.create_module(request)
        return CreateModuleResponse(id=result["id"], status=result["status"])

    async def fetch_modules(
            self, request: FetchModulesRequest) -> FetchModulesResponse:
        if not request.user_id:
            raise HTTPException(status_code=400, detail="Missing 'userId'")

        modules = await self.service.fetch_modules(request.user_id)
        return FetchModulesResponse(modules=modules)

    async def get_module_by_id(self, module_id: str) -> ModuleData:
        """Get a single module by ID"""
        if not module_id:
            raise HTTPException(status_code=400, detail="Missing 'id'")

        module = await self.service.get_module_by_id(module_id)
        if not module:
            raise HTTPException(
                status_code=404,
                detail=f"Module with id {module_id} not found")
        return module


controller = ModuleController()


@router.post("/modules/create", tags=["Modules", "Create"])
async def create_module(request: CreateModuleRequest) -> CreateModuleResponse:
    return await controller.create_module(request)


@router.post("/modules/fetch", tags=["Modules", "Read"])
async def fetch_modules(request: FetchModulesRequest) -> FetchModulesResponse:
    return await controller.fetch_modules(request)


@router.get("/modules/fetch/{module_id}", tags=["Modules", "Read"])
async def get_module_by_id(module_id: str) -> ModuleData:
    """Get a single module by ID"""
    return await controller.get_module_by_id(module_id)
