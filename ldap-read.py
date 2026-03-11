#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gitlab
import sys
import json
import ldap
import ldap.asyncsearch
import logging
from services.ldap_service import LdapService

config = None

def init():
    global config

    print('Initializing.')
    with open('config.json') as f:
        config = json.load(f)

    if config is None:
        print('Could not load config.json, check if the file is present.')
        print('Aborting.')
        sys.exit(1)

    print('Done.')
    print('Updating logger configuration')

    if not config['gitlab']['group_visibility']:
        config['gitlab']['group_visibility'] = 'private'

    log_level = getattr(
        logging,
        str(config.get('log_level', 'INFO')).upper(),
        logging.INFO
    )

    handlers = []

    if config.get('log'):
        handlers.append(logging.FileHandler(config['log']))

    handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        handlers=handlers,
        force=True
    )

    print('Done.')





if __name__ == "__main__":
    init()

    ldap_service = LdapService(config)
    logging.info('Groups currently in LDAP : %s' % str.join(', ', ldap_service.list_groups()))
