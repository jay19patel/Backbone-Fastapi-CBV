import httpx
import asyncio

BASE_URL = "http://127.0.0.1:8000"

async def verify_get_blogs():
    async with httpx.AsyncClient() as client:
        print(f"Testing GET {BASE_URL}/blogs/?page=1&page_size=10")
        try:
            resp = await client.get(f"{BASE_URL}/blogs/?page=1&page_size=10")
            print(f"Status Code: {resp.status_code}")
            if resp.status_code == 200:
                print("Response JSON (first item):")
                data = resp.json()
                items = data.get("items", [])
                if items:
                    print(items[0])
                else:
                    print("No items found, but request succeeded.")
                print("SUCCESS: GET /blogs/ is working.")
            else:
                print(f"FAILED: {resp.text}")
        except Exception as e:
            print(f"Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_get_blogs())
