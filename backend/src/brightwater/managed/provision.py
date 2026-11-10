"""Update owned webhook tools without changing IDs referenced by native tests."""


def retain_tools(client, existing, desired):
    known = {}
    for tool_id in existing.get("conversation_config", {}).get("agent", {}).get("prompt", {}).get("tool_ids", []):
        response = client.get("/v1/convai/tools/" + tool_id)
        response.raise_for_status()
        tool = response.json()["tool_config"]
        if tool["name"] in known:
            raise ValueError("Duplicate owned tool name; reconcile before provisioning")
        known[tool["name"]] = (tool_id, tool)
    ids = []
    for tool in desired:
        if tool["type"] != "webhook":
            raise ValueError("Only business webhook tools belong in this registry")
        previous = known.get(tool["name"])
        if previous:
            tool_id, old = previous
            if old.get("api_schema", {}).get("url") != tool["api_schema"]["url"]:
                raise ValueError("Refusing to repoint a tool owned by a different service")
            response = client.patch("/v1/convai/tools/" + tool_id, json={"tool_config": tool})
        else:
            response = client.post("/v1/convai/tools", json={"tool_config": tool})
        response.raise_for_status()
        ids.append(previous[0] if previous else response.json()["id"])
    return ids
