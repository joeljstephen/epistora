from __future__ import annotations


def test_views_api_route_exists():
    from app.api.routes_views import router

    route = router.routes[0]
    assert route.path == "/views/rebuild"
