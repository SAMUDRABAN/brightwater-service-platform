import httpx
import pytest

from brightwater.managed.provision import retain_tools


def test_reprovision_preserves_tool_identity_and_updates_its_schema():
    requests = []
    def handle(request):
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"tool_config": {"name": "check_availability", "api_schema": {"url": "https://owned.test/tools/check"}}})
        return httpx.Response(200, json={"id": "new-review"})
    with httpx.Client(base_url="https://provider.test", transport=httpx.MockTransport(handle)) as client:
        existing = {"conversation_config": {"agent": {"prompt": {"tool_ids": ["original-availability"]}}}}
        desired = [{"type": "webhook", "name": "check_availability", "api_schema": {"url": "https://owned.test/tools/check"}},
                   {"type": "webhook", "name": "review_arrangement", "api_schema": {"url": "https://owned.test/tools/review"}}]
        assert retain_tools(client, existing, desired) == ["original-availability", "new-review"]
        assert requests == [("GET", "/v1/convai/tools/original-availability"), ("PATCH", "/v1/convai/tools/original-availability"), ("POST", "/v1/convai/tools")]
        desired[0]["api_schema"]["url"] = "https://another.test/tool"
        with pytest.raises(ValueError, match="different service"):
            retain_tools(client, existing, desired)
