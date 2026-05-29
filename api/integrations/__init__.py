"""
integrations — one module per external platform.

Each submodule exposes a thin client that handles authentication,
HTTP requests, and response parsing for a single data source.  All
error handling and data normalisation happens here so the agent layer
receives clean, typed data.
"""
