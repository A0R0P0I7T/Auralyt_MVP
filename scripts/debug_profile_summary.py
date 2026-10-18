import sys
sys.path.insert(0, ".")
import asyncio
import traceback
from app.db.session import async_session_factory
from app.services.profiler_service import ProfilerService

async def main():
    async with async_session_factory() as db:
        try:
            res = await ProfilerService.get_brand_profile_summary("5c785452-feea-4038-9a29-eea7b6252ec0", db)
            print("Successfully retrieved profile summary!")
            print(f"Pricing count: {len(res['pricing_information'])}")
            from app.schemas.profile_summary import ProfileSummaryResponse
            validated = ProfileSummaryResponse.model_validate(res)
            print("Successfully validated with ProfileSummaryResponse!")
        except Exception as e:
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
