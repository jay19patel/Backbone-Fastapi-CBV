"""
pages/contact.py
----------------
Server-rendered contact form page (optional HTML layer).
This is a lightweight stub — the actual contact form data
is stored via the REST API at POST /api/content/contact.
"""

from fastapi import APIRouter

router = APIRouter()

# Placeholder — no server-side HTML pages needed for this project.
# The Next.js frontend handles all UI; this stub exists so main.py
# can import it without error. Add GenericFormView pages here later.
