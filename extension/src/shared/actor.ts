// Who the extension says it is on every request to the engine (:7700). The engine's HTTP guard (understudy_engine/http_guard.py) requires an
// explicit actor on any request that carries an Origin, and accepts the value "extension" from a chrome-extension:// origin for
// POST /events. Nothing else is sent with it: no token, no secret, no identifier beyond the person and role the events already carry.
export const ACTOR_HEADER = "x-understudy-actor";
export const ACTOR = "extension";
