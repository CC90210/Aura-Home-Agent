---
description: "Control Home Assistant scenes, lights, and devices via MCP. Use when CC says 'set the vibe', 'turn on lights', 'movie mode', etc."
---
Use the ha-mcp MCP tools to control Home Assistant devices.

Common operations:
- List entities: use ha-mcp list tools to find device entity IDs
- Control lights: `light.turn_on`, `light.turn_off` with brightness/color
- Activate scenes: `scene.turn_on` with scene entity ID
- Climate: `climate.set_temperature` with target temp

Always confirm the action was executed. If a device isn't responding, check its entity_id exists first.
