from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up `key` in `dictionary` from a template. Needed because Django's
    built-in dot-lookup doesn't reliably resolve integer dict keys (e.g.
    usage_by_user[user.pk] where the dict is keyed by int, not str)."""
    if dictionary is None:
        return None
    return dictionary.get(key)
