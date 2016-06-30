from __future__ import unicode_literals

from core.observables import Observable, Url, Hostname
from core.indicators import Indicator
from core.errors import ObservableValidationError
from core.helpers import del_from_set, iterify, refang

# load analyzers
from plugins.analytics.process_hostnames import ProcessHostnames
from plugins.analytics.process_url import ProcessUrl

analyzers = {
    Hostname: [ProcessHostnames],
    Url: [ProcessUrl],
}


def derive(observables):
    """Indicate that the module needs a specific attribute to work properly.

    This function is only useful in abstract modules, in order to make sure
    that modules that inherit from this class correctly defines needed class
    attributes.

    Args:
        variables: a string or an array of strings containing the name of
            needed class attributes.

    Raises:
        ModuleInitializationError: One of the needed attributes is not
            correctly defined.
    """

    new = []
    for observable in iterify(observables):
        try:
            t = Observable.guess_type(observable)
            for a in analyzers.get(t, []):
                new.extend([n for n in a.analyze_string(observable) if n and n not in observables])
        except ObservableValidationError:
            pass

    if len(new) == 0:
        return observables
    else:
        return derive(new + observables)


def match_observables(observables, save_matches=False):
    # Remove empty observables
    observables = [refang(observable) for observable in observables if observable]
    extended_query = set(observables) | set(derive(observables))

    data = {
        "matches": [],
        "unknown": set(observables),
        "entities": {},
        "known": [],
        "neighbors": [],
    }

    # add to "known"
    for o in Observable.objects(value__in=list(extended_query)):
        data['known'].append(o.info())
        del_from_set(data['unknown'], o.value)

        for link, node in (o.incoming()):
            if isinstance(node, Observable):
                if (link.src.value not in extended_query or link.dst.value not in extended_query) and node.tags:
                    data['neighbors'].append((link.info(), node.info()))

        for nodes in o.neighbors("Entity").values():
            for l, node in nodes:
                # add node name and link description to indicator
                node_data = {"entity": node.type, "name": node.name, "link_description": l.description}

                # uniquely add node information to related entitites
                ent = data['entities'].get(node.name, node.info())
                if 'matches' not in ent:
                    ent['matches'] = {"observables": []}
                if 'observables' not in ent['matches']:
                    ent['matches']['observables'] = []

                info = node.info()
                o_info = o.info()
                info['matched_observable'] = {
                    "value": o_info['value'],
                    "tags": [t['name'] for t in o_info['tags']],
                    "human_url": o_info['human_url'],
                    "url": o_info['url']
                }
                if info not in ent['matches']['observables']:
                    ent['matches']['observables'].append(info)
                data['entities'][node.name] = ent

    # add to "matches"
    for o, i in Indicator.search(extended_query):
        if save_matches:
            o = Observable.add_text(o)
        else:
            o = Observable.guess_type(o)(value=o)
            try:
                o.validate()
            except ObservableValidationError:
                pass
            try:
                o = Observable.objects.get(value=o.value)
            except Exception:
                pass

        match = i.info()
        match.update({"observable": o.info(), "related": [], "suggested_tags": set()})

        for nodes in i.neighbors("Entity").values():
            for l, node in nodes:
                # add node name and link description to indicator
                node_data = {"entity": node.type, "name": node.name, "link_description": l.description}
                match["related"].append(node_data)

                # uniquely add node information to related entitites
                ent = data['entities'].get(node.name, node.info())
                if 'matches' not in ent:
                    ent['matches'] = {"indicators": []}
                if 'indicators' not in ent['matches']:
                    ent['matches']['indicators'] = []

                info = i.info()
                info['matched_observable'] = o.value
                if info not in ent['matches']['indicators']:
                    ent['matches']['indicators'].append(info)
                data['entities'][node.name] = ent

                o_tags = o.get_tags()
                [match["suggested_tags"].add(tag) for tag in node.generate_tags() if tag not in o_tags]

        data["matches"].append(match)

    data['entities'] = data['entities'].values()
    return data
