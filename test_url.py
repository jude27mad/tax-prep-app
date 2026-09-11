def _sanitize_redirect(target: str) -> str:
    if not target or not target.startswith("/"):
        return "/ui/"
    if target.startswith("//") or target.startswith("/\\"):
        return "/ui/"
    return target

print(_sanitize_redirect("/ui/profiles"))
print(_sanitize_redirect("//evil.com"))
print(_sanitize_redirect("/\\evil.com"))
print(_sanitize_redirect("https://evil.com"))
