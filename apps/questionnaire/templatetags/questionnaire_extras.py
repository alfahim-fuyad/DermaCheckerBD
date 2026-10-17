"""Template tags for the questionnaire app.

The questionnaire template renders Yes / No / Unsure radios for each
question. To preserve the user's previously-selected answer after a POST
(and after Bangla/English toggling), we need to look up `answers[q.id]`
inside a Django template — but Django templates do not support dict
lookups by a *variable* key directly (`answers.q.id` is parsed as
`answers['q']['id']`, not `answers[q.id]`).

The `dict_get` filter below bridges that gap. Usage:

    {% load questionnaire_extras %}
    {% if answers|dict_get:q.id == 'yes' %}checked{% endif %}
"""
from django import template

register = template.Library()


@register.filter(name="dict_get")
def dict_get(mapping, key):
    """Return mapping[key] (or '' when mapping is None or key is missing).

    Works with both dict and Django QuerySet-like objects that expose
    `__getitem__`. Returns '' (the falsy empty string) when the lookup
    fails so the template can safely write `{% if x|dict_get:k %}`.
    """
    if mapping is None:
        return ""
    try:
        return mapping.get(key, "")
    except AttributeError:
        try:
            return mapping[key]
        except (KeyError, TypeError, IndexError):
            return ""
    except (KeyError, TypeError, IndexError):
        return ""
