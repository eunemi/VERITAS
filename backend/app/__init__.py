"""Veritas verification API.

Layered so that dependencies point one way only: ``api`` depends on ``services``,
``services`` on the provider seams and ``database``, and ``core``/``utils`` depend
on nothing inside the application. Nothing below ``api`` imports FastAPI.
"""
