import json
from typing import TypedDict, Optional, List, Dict, Any

from langgraph.graph import StateGraph, END

import db
from groq_client import ask_json
from weather_client import geocode, get_weather


class TripState(TypedDict, total=False):
    trip_id: str
    origin: str
    destination: str
    start_date: str
    end_date: str
    budget: Optional[float]
    interests: List[str]
    travelers: int
    planner: Dict[str, Any]
    budget_result: Dict[str, Any]
    local_info: Dict[str, Any]
    transport: Dict[str, Any]
    itinerary: Dict[str, Any]


def mark_step(trip_id, step):
    db.mark_step(trip_id, step)


def planner_node(state: TripState) -> dict:
    mark_step(state["trip_id"], "planner")
    system = (
        "You are the planning agent in a trip-planning system for Indian "
        "travelers. Given an origin, destination, date range and interests, "
        "produce a rough day-by-day skeleton. The ENTIRE trip takes place "
        "in and around the destination city only - do not route the "
        "traveler through other cities or plan stopovers elsewhere, even "
        "if a real-world road/rail route would pass through them. The "
        "first day covers arrival at the destination and the last day "
        "covers departure; every day in between must be themed around "
        'things to do inside the destination itself. Respond with ONLY '
        'JSON: {"days": [{"date": "YYYY-MM-DD", "theme": "short theme"}]}'
    )
    user = (
        f"Origin: {state.get('origin', '')}\n"
        f"Destination: {state['destination']}\n"
        f"Dates: {state['start_date']} to {state['end_date']}\n"
        f"Interests: {', '.join(state.get('interests') or []) or 'general sightseeing'}"
    )
    plan = ask_json(system, user, max_tokens=800)
    return {"planner": {"days": plan.get("days", [])}}


def budget_node(state: TripState) -> dict:
    mark_step(state["trip_id"], "budget")
    days = state.get("planner", {}).get("days", [])
    target_budget = state.get("budget")
    travelers = state.get("travelers", 1)
    system = (
        "You are the budget checking agent in a trip-planning system for "
        "Indian travelers. Given an origin, destination, trip length, "
        "number of travelers and target budget, estimate a realistic cost "
        "breakdown in INR for the WHOLE GROUP together. Transport and food "
        "scale per traveler (each person needs their own seat/meal); "
        "lodging usually does not scale linearly since travelers can share "
        "rooms - use judgement (e.g. 2 people can often share one room, "
        "so lodging for 2 isn't simply double that for 1). Transport must "
        "include a ROUND TRIP (there and back) for every traveler, not just "
        "one leg for one person. Be realistic even if the target budget is "
        "unrealistically low or high for the trip - do not distort your "
        "estimate to force it to fit the target. Respond "
        'with ONLY JSON: {"currency": "INR", "estimatedTotal": number, '
        '"breakdown": {"transport": number, "lodging": number, "food": number, '
        '"activities": number}, "withinBudget": boolean, "note": "one short sentence"}'
    )
    user = (
        f"Origin: {state.get('origin', '')}\n"
        f"Destination: {state['destination']}\n"
        f"Trip length: {len(days)} days\n"
        f"Number of travelers: {travelers}\n"
        f"Target budget for the whole group (INR): {target_budget or 'not specified, suggest a reasonable mid-range budget in INR'}"
    )
    result = ask_json(system, user, temperature=0.3, max_tokens=500)

    # Don't trust the model's own withinBudget judgment - compute it deterministically.
    if target_budget:
        try:
            result["withinBudget"] = float(result.get("estimatedTotal", 0)) <= float(target_budget)
        except (TypeError, ValueError):
            pass

    return {"budget_result": result}


def local_info_node(state: TripState) -> dict:
    mark_step(state["trip_id"], "localInfo")
    coords = geocode(state["destination"])
    weather = get_weather(coords, state["start_date"], state["end_date"]) if coords else {}

    system = (
        "You are the local info agent in a trip-planning system. Given a "
        "destination and interests, suggest 6 to 10 specific, real "
        "attractions (not generic categories) and 5 to 6 short, practical "
        'local tips. Respond with ONLY JSON: {"attractions": [{"name": '
        '"...", "why": "short reason"}], "tips": ["short practical tip", "..."]}'
    )
    user = (
        f"Destination: {state['destination']}\n"
        f"Interests: {', '.join(state.get('interests') or []) or 'general sightseeing'}"
    )
    info = ask_json(system, user, temperature=0.5, max_tokens=1200)
    info["weather"] = weather
    info["coordinates"] = {"lat": coords[0], "lon": coords[1]} if coords else None
    return {"local_info": info}


def transport_node(state: TripState) -> dict:
    mark_step(state["trip_id"], "transport")
    travelers = state.get("travelers", 1)
    system = (
        "You are the transport agent in a trip-planning system for Indian "
        "travelers. Given an origin, destination and number of travelers, "
        "list realistic ways to make that journey - choose from flight, "
        "train, bus, self-drive/car, whichever are actually practical for "
        "this specific route. The costRange for each option must be the "
        "ROUND TRIP cost for ALL travelers combined (not one leg, not one "
        "person) - state this clearly, e.g. 'round trip for 3 travelers'. "
        "Self-drive/car cost does not multiply per traveler (it's one "
        "vehicle) - only flight/train/bus costs scale with traveler count. "
        "Give an approximate travel duration for one leg. "
        'Respond with ONLY JSON: {"options": [{"mode": "Flight", "costRange": '
        '"₹3,500–₹6,000 round trip", "duration": "1h 30m", "note": "short practical note"}], '
        '"recommended": "one short sentence recommending the best option and why"}'
    )
    user = f"Origin: {state.get('origin', '')}\nDestination: {state['destination']}\nNumber of travelers: {travelers}"
    return {"transport": ask_json(system, user, temperature=0.4, max_tokens=600)}


def writer_node(state: TripState) -> dict:
    mark_step(state["trip_id"], "writer")
    system = (
        "You are the final itinerary writer agent in a trip-planning system "
        "for Indian travelers. Combine the rough day-by-day plan, the budget "
        "estimate, the local info and the transport options into one "
        "detailed, polished itinerary for the whole group of travelers, "
        "all costs in INR representing the group total (not per-person "
        "unless stated). The ENTIRE trip "
        "takes place in and around the destination city only - never plan "
        "days around other cities or a multi-city road trip, even if one "
        "would be geographically plausible; only the first day (arrival) "
        "and last day (departure) mention travel. Transport cost in the "
        "budget breakdown must be the ROUND TRIP cost. For each day, "
        "write 4 to 6 specific activities using real place names drawn "
        "from the local info provided (attractions, markets, food spots), "
        "each prefixed with a time of day where it makes sense, e.g. "
        "'Morning: Visit X and explore the old bazaar.' Spread the "
        "attractions and tips across the days rather than reusing the same "
        "one or two repeatedly. Respond with ONLY JSON: "
        '{"origin": "...", "destination": "...", "days": [{"date": '
        '"YYYY-MM-DD", "title": "...", "activities": ["...", "..."]}], '
        '"budget": {"currency": "INR", "estimatedTotal": number, "breakdown": '
        '{"transport": number, "lodging": number, "food": number, '
        '"activities": number}, "withinBudget": boolean, "note": "..."}, '
        '"transport": {"options": [{"mode": "...", "costRange": "...", '
        '"duration": "...", "note": "..."}], "recommended": "..."}, '
        '"tips": ["...", "..."]}'
    )
    user = json.dumps({
        "origin": state.get("origin"),
        "destination": state["destination"],
        "travelers": state.get("travelers", 1),
        "roughPlan": state.get("planner"),
        "budgetEstimate": state.get("budget_result"),
        "localInfo": state.get("local_info"),
        "transportOptions": state.get("transport"),
    })
    itinerary = ask_json(system, user, max_tokens=5000)
    itinerary["coordinates"] = (state.get("local_info") or {}).get("coordinates")
    itinerary["weather"] = (state.get("local_info") or {}).get("weather")
    itinerary["attractions"] = (state.get("local_info") or {}).get("attractions")
    itinerary["travelers"] = state.get("travelers", 1)
    itinerary.setdefault("origin", state.get("origin"))
    itinerary.setdefault("transport", state.get("transport"))

    # Don't trust the model's own withinBudget judgment - compute it deterministically.
    target_budget = state.get("budget")
    if target_budget and itinerary.get("budget"):
        try:
            itinerary["budget"]["withinBudget"] = (
                float(itinerary["budget"].get("estimatedTotal", 0)) <= float(target_budget)
            )
        except (TypeError, ValueError):
            pass

    db.save_itinerary(state["trip_id"], itinerary)
    return {"itinerary": itinerary}


def build_graph():
    graph = StateGraph(TripState)
    graph.add_node("planner", planner_node)
    graph.add_node("budget", budget_node)
    graph.add_node("local_info", local_info_node)
    graph.add_node("transport", transport_node)
    graph.add_node("writer", writer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "budget")
    graph.add_edge("planner", "local_info")
    graph.add_edge("planner", "transport")
    graph.add_edge("budget", "writer")
    graph.add_edge("local_info", "writer")
    graph.add_edge("transport", "writer")
    graph.add_edge("writer", END)

    return graph.compile()