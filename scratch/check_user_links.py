import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from backbone.core.database import init_database
from backbone.core.models import User, Attachment
from backbone.core.repository import BeanieRepository

async def check():
    detected = BeanieRepository.detect_populate_fields(User)
    print("Detected Populate Fields for User:")
    import json
    # Use a custom serializer for non-JSON serializable objects
    def default(o):
        if isinstance(o, type):
            return o.__name__
        return str(o)
    print(json.dumps(detected, indent=2, default=default))

if __name__ == "__main__":
    asyncio.run(check())
