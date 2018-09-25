PATHPATTERN = '^[A-Za-z0-9]+?(?!.*?/[\.]{1,}/)([A-Za-z0-9\.\-_/])+?[A-Za-z0-9]+?$'

FILEINFOSCHEMA = {
    'type': 'object',
    'required': ['md5', 'size', 'filename'],
    'properties': {
        "size": {'type': 'integer', 'minimum': 30},
        'md5': {'type': 'string', 'format': 'md5'},
        "ext": {'type': 'string', 'minimum': 3, 'maximum': 5},
        "filename": {'type': 'string', "pattern": PATHPATTERN},
        "overwrite": {'oneOf':
                          [{'type': 'null'},
                           {'type': 'string', "pattern": PATHPATTERN}]
                      }
    }
}
