from typing import Dict, List
from datetime import datetime
from bson import ObjectId
from infrastructure.database import Database
from api.schemas.requests import CreateAssignmentRequest
from api.schemas.responses import (
    AssignmentData,
    FetchAssignmentsResponse,
    FetchAssignedPlansResponse,
    TrainingPlanDetails,
    ModuleDetails,
    SimulationDetails,
    Stats,
    StatsData
)
from fastapi import HTTPException

from utils.logger import Logger  # <-- Import your custom logger

logger = Logger.get_logger(__name__)


class AssignmentService:

    def __init__(self):
        self.db = Database()
        logger.info("AssignmentService initialized.")

    async def create_assignment(self, request: CreateAssignmentRequest) -> Dict:
        """Create a new assignment"""
        logger.info("Received request to create a new assignment.")
        logger.debug(f"Assignment request data: {request.dict()}")
        try:
            assignment_doc = {
                "id": request.id,
                "name": request.name,
                "type": request.type,
                "startDate": request.start_date,
                "endDate": request.end_date,
                "teamId": [team.dict() for team in request.team_id],
                "traineeId": request.trainee_id,
                "createdBy": request.user_id,
                "createdAt": datetime.utcnow(),
                "lastModifiedBy": request.user_id,
                "lastModifiedAt": datetime.utcnow(),
                "status": "active"
            }

            result = await self.db.assignments.insert_one(assignment_doc)
            assignment_id = str(result.inserted_id)
            logger.info(f"Assignment inserted with ID: {assignment_id}")

            # Process trainee IDs
            for trainee_id in request.trainee_id:
                logger.debug(f"Processing trainee_id={trainee_id} for assignment={assignment_id}")
                await self._process_user_assignment(trainee_id, assignment_id)

            # Process team members
            for team in request.team_id:
                if team.leader and team.leader.user_id:
                    logger.debug(f"Processing team leader={team.leader.user_id} for assignment={assignment_id}")
                    await self._process_user_assignment(team.leader.user_id, assignment_id, team.leader.dict())

                if team.team_members:
                    for member in team.team_members:
                        if member.user_id:
                            logger.debug(f"Processing team member={member.user_id} for assignment={assignment_id}")
                            await self._process_user_assignment(member.user_id, assignment_id, member.dict())

            logger.info("Assignment creation completed successfully.")
            return {"id": assignment_id, "status": "success"}
        except Exception as e:
            logger.error(f"Error creating assignment: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error creating assignment: {str(e)}")

    async def _process_user_assignment(self, user_id: str, assignment_id: str, user_data: Dict = None) -> None:
        """Process user document creation or update for assignments"""
        logger.debug(f"Processing user assignment for user_id={user_id}, assignment_id={assignment_id}")
        try:
            existing_user = await self.db.users.find_one({"_id": user_id})
            if existing_user:
                logger.debug(f"User {user_id} found. Updating assignments array.")
                update_doc = {"$addToSet": {"assignments": assignment_id}}

                if user_data:
                    logger.debug(f"Updating user fields with: {user_data}")
                    update_doc["$set"] = {
                        "first_name": user_data.get("first_name"),
                        "last_name": user_data.get("last_name"),
                        "email": user_data.get("email"),
                        "phone_no": user_data.get("phone_no"),
                        "fullName": user_data.get("fullName"),
                        "lastModifiedAt": datetime.utcnow()
                    }

                await self.db.users.update_one({"_id": user_id}, update_doc)
                logger.debug(f"User {user_id} assignments array updated successfully.")
            else:
                logger.debug(f"User {user_id} does not exist. Creating new user document.")
                new_user = {
                    "_id": user_id,
                    "assignments": [assignment_id],
                    "createdAt": datetime.utcnow(),
                    "lastModifiedAt": datetime.utcnow()
                }

                if user_data:
                    logger.debug(f"Adding user data to new user: {user_data}")
                    new_user.update({
                        "first_name": user_data.get("first_name"),
                        "last_name": user_data.get("last_name"),
                        "email": user_data.get("email"),
                        "phone_no": user_data.get("phone_no"),
                        "fullName": user_data.get("fullName")
                    })

                await self.db.users.insert_one(new_user)
                logger.debug(f"New user {user_id} created successfully.")
        except Exception as e:
            logger.error(f"Error processing user assignment: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing user assignment: {str(e)}"
            )

    async def fetch_assignments(self) -> List[AssignmentData]:
        """Fetch all assignments"""
        logger.info("Fetching all assignments.")
        try:
            cursor = self.db.assignments.find({})
            assignments = []

            async for doc in cursor:
                team_ids = []
                if doc.get("teamId"):
                    for team in doc["teamId"]:
                        if isinstance(team, dict) and team.get("team_id"):
                            team_ids.append(team["team_id"])

                assignment = AssignmentData(
                    id=doc.get("id", ""),
                    name=doc.get("name", ""),
                    type=doc.get("type", ""),
                    start_date=doc.get("startDate", ""),
                    end_date=doc.get("endDate", ""),
                    team_id=team_ids,
                    trainee_id=doc.get("traineeId", []),
                    created_by=doc.get("createdBy", ""),
                    created_at=doc.get("createdAt", datetime.utcnow()).isoformat(),
                    last_modified_by=doc.get("lastModifiedBy", ""),
                    last_modified_at=doc.get("lastModifiedAt", datetime.utcnow()).isoformat(),
                    status=doc.get("status", "")
                )
                assignments.append(assignment)

            logger.info(f"Fetched {len(assignments)} assignment(s) from the database.")
            return assignments
        except Exception as e:
            logger.error(f"Error fetching assignments: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error fetching assignments: {str(e)}")

    async def fetch_assigned_plans(self, user_id: str) -> FetchAssignedPlansResponse:
        """Fetch assigned training plans with nested details"""
        logger.info(f"Fetching assigned training plans for user_id={user_id}")
        try:
            user = await self.db.users.find_one({"_id": user_id})
            if not user:
                logger.warning(f"User {user_id} not found.")
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")

            assignment_ids = user.get("assignments", [])
            logger.debug(f"Assignment IDs for user {user_id}: {assignment_ids}")

            object_ids = [ObjectId(aid) for aid in assignment_ids]
            assignments = await self.db.assignments.find({
                "_id": {"$in": object_ids},
                "status": "active"
            }).to_list(None)

            training_plans = []
            modules = []
            simulations = []
            total_simulations = 0

            for assignment in assignments:
                logger.debug(f"Processing assignment: {assignment}")
                if assignment["type"] == "TrainingPlan":
                    training_plan = await self.db.training_plans.find_one({"_id": ObjectId(assignment["id"])})
                    if training_plan:
                        plan_modules = []
                        plan_total_simulations = 0
                        plan_est_time = 0

                        for added_obj in training_plan.get("addedObject", []):
                            if added_obj["type"] == "module":
                                module_details = await self._get_module_details(
                                    added_obj["id"],
                                    assignment["endDate"],
                                    assignment["id"]
                                )
                                if module_details:
                                    plan_modules.append(module_details)
                                    plan_total_simulations += module_details.total_simulations
                                    plan_est_time += sum(sim.estTime for sim in module_details.simulations)
                                    total_simulations += module_details.total_simulations

                            elif added_obj["type"] == "simulation":
                                sim_details = await self._get_simulation_details(
                                    added_obj["id"],
                                    assignment["endDate"],
                                    assignment["id"]
                                )
                                if sim_details:
                                    plan_modules.append(
                                        ModuleDetails(
                                            id=sim_details.simulation_id,
                                            name=sim_details.name,
                                            total_simulations=1,
                                            average_score=0,
                                            due_date=assignment["endDate"],
                                            status="not_started",
                                            simulations=[sim_details]
                                        )
                                    )
                                    plan_total_simulations += 1
                                    plan_est_time += sim_details.estTime
                                    total_simulations += 1

                        training_plans.append(
                            TrainingPlanDetails(
                                id=str(training_plan["_id"]),
                                name=training_plan.get("name", ""),
                                completion_percentage=0,
                                total_modules=len(plan_modules),
                                total_simulations=plan_total_simulations,
                                est_time=plan_est_time,
                                average_sim_score=0,
                                due_date=assignment["endDate"],
                                status="not_started",
                                modules=plan_modules
                            )
                        )
                elif assignment["type"] == "Module":
                    module_details = await self._get_module_details(
                        assignment["id"],
                        assignment["endDate"],
                        assignment["id"]
                    )
                    if module_details:
                        modules.append(module_details)
                        total_simulations += module_details.total_simulations
                elif assignment["type"] == "Simulation":
                    sim_details = await self._get_simulation_details(
                        assignment["id"],
                        assignment["endDate"],
                        assignment["id"]
                    )
                    if sim_details:
                        simulations.append(sim_details)
                        total_simulations += 1

            stats = Stats(
                simulation_completed=StatsData(
                    total_simulations=total_simulations,
                    completed_simulations=0,
                    percentage=0
                ),
                timely_completion=StatsData(
                    total_simulations=total_simulations,
                    completed_simulations=0,
                    percentage=0
                ),
                average_sim_score=0,
                highest_sim_score=0
            )

            logger.info(
                f"Finished fetching assigned plans for user_id={user_id}. "
                f"Total simulations found: {total_simulations}"
            )
            return FetchAssignedPlansResponse(
                training_plans=training_plans,
                modules=modules,
                simulations=simulations,
                stats=stats
            )
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error fetching assigned plans: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching assigned plans: {str(e)}"
            )

    async def _get_module_details(self, module_id: str, due_date: str, assignment_id: str) -> ModuleDetails:
        """Helper method to get module details"""
        logger.debug(f"Fetching module details for module_id={module_id}")
        try:
            module = await self.db.modules.find_one({"_id": ObjectId(module_id)})
            if not module:
                logger.warning(f"Module {module_id} not found.")
                return None

            module_simulations = []
            for sim_id in module.get("simulationIds", []):
                sim_details = await self._get_simulation_details(sim_id, due_date, assignment_id)
                if sim_details:
                    module_simulations.append(sim_details)

            logger.debug(f"Module {module_id} has {len(module_simulations)} simulation(s).")
            return ModuleDetails(
                id=str(module["_id"]),
                name=module.get("name", ""),
                total_simulations=len(module_simulations),
                average_score=0,
                due_date=due_date,
                status="not_started",
                simulations=module_simulations
            )
        except Exception as e:
            logger.error(f"Error fetching module details: {str(e)}", exc_info=True)
            return None

    async def _get_simulation_details(self, sim_id: str, due_date: str, assignment_id: str) -> SimulationDetails:
        """Helper method to get simulation details"""
        logger.debug(f"Fetching simulation details for sim_id={sim_id}")
        try:
            sim = await self.db.simulations.find_one({"_id": ObjectId(sim_id)})
            if not sim:
                logger.warning(f"Simulation {sim_id} not found.")
                return None

            logger.debug(f"Simulation {sim_id} retrieved successfully.")
            return SimulationDetails(
                simulation_id=str(sim["_id"]),
                name=sim.get("name", ""),
                type=sim.get("type", ""),
                level="beginner",  # Default value
                estTime=sim.get("estimatedTimeToAttemptInMins", 0),
                dueDate=due_date,
                status="not_started",
                highest_attempt_score=0,
                assignment_id=assignment_id
            )
        except Exception as e:
            logger.error(f"Error fetching simulation details: {str(e)}", exc_info=True)
            return None

