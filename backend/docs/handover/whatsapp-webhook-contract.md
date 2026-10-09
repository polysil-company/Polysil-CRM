# WhatsApp webhook capture

Nothing for the frontend to build. Two public endpoints now receive 11za's calls (incoming WhatsApp messages and delivery updates) and store them for the backend. They are not in the OpenAPI schema and need no screen.

When step two lands, inbound WhatsApp messages will create leads like the website form does, with the source `whatsapp`. The lead screens need no change for that; the source list already comes from the lookups.
