"""Service layer for Atelier — storage, embeddings, retrieval, metrics.

Routers stay thin and call into these modules; nothing here imports FastAPI,
so every service is testable without spinning up the HTTP app.
"""
