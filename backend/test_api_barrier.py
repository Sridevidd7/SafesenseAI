import asyncio
import httpx
from main import app

async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("=== TESTING ANALYZE API WITH BARRIER DETECTION ===")
        
        # Test case 1
        res1 = await client.post("/api/analyze-report", json={
            "report_text": "worker entered tank without gas testing",
            "severity": "High",
            "report_type": "Near Miss"
        })
        assert res1.status_code == 200, res1.text
        data1 = res1.json()
        print("Case 1 Barrier Failures:", data1.get("barrier_failures"))
        print("Case 1 Barrier Evidence:", data1.get("barrier_evidence"))
        assert "Gas Testing Not Completed" in data1.get("barrier_failures"), "Gas Testing Not Completed missing"

        # Test case 2
        res2 = await client.post("/api/analyze-report", json={
            "report_text": "technician entered vessel no atmospheric test done",
            "severity": "High",
            "report_type": "Near Miss"
        })
        assert res2.status_code == 200, res2.text
        data2 = res2.json()
        print("Case 2 Barrier Failures:", data2.get("barrier_failures"))
        assert "Gas Testing Not Completed" in data2.get("barrier_failures")

        # Test case 3
        res3 = await client.post("/api/analyze-report", json={
            "report_text": "no permit was issued before entry",
            "severity": "Medium",
            "report_type": "Unsafe Act"
        })
        assert res3.status_code == 200, res3.text
        data3 = res3.json()
        print("Case 3 Barrier Failures:", data3.get("barrier_failures"))
        assert "Permit Not Obtained" in data3.get("barrier_failures")

        # Test case 4
        res4 = await client.post("/api/analyze-report", json={
            "report_text": "worker not tied off at height",
            "severity": "High",
            "report_type": "Near Miss"
        })
        assert res4.status_code == 200, res4.text
        data4 = res4.json()
        print("Case 4 Barrier Failures:", data4.get("barrier_failures"))
        assert "Fall Protection Not Used" in data4.get("barrier_failures")

        print("\n>>> ALL API ANALYZE TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    asyncio.run(main())
