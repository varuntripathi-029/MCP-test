import pytest


@pytest.mark.mcp
async def test_lists_resources(mcp_client):
    resources = await mcp_client.list_resources()
    assert isinstance(resources, list)


@pytest.mark.mcp
async def test_reads_first_resource(mcp_client):
    resources = await mcp_client.list_resources()
    if not resources:
        pytest.skip("No resources exposed by the configured MCP server")

    contents = await mcp_client.read_resource(resources[0]["uri"])
    assert len(contents) > 0
