#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gitlab
import sys
import json
import ldap
import ldap.asyncsearch
import logging


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


class LdapService:

    def __init__(self):
        self.l = None
        
        if not config['ldap']['url']:
            logging.error('You should configure LDAP in config.json')
            sys.exit(1)

        try:
            self.l = ldap.initialize(uri=config['ldap']['url'])
            self.l.simple_bind_s(config['ldap']['bind_dn'], config['ldap']['password'])
        except:
            logging.error('Error while connecting')
            sys.exit(1)

        logging.info('Done.')


    def list_groups(self):
        logging.info('Getting all groups from LDAP.')
        ldap_groups = []
        ldap_groups_names = []

        if not config['ldap']['group_attribute'] and not config['ldap']['group_prefix']:
            filterstr = '(objectClass=group)'
        else:
            if config['ldap']['group_attribute'] and config['ldap']['group_prefix']:
                logging.error('You should set "group_attribute" or "group_prefix" but not both in config.json')
                sys.exit(1)
            else:
                if config['ldap']['group_attribute']:
                    filterstr = '(&(objectClass=group)(%s=gitlab_sync))' % config['ldap']['group_attribute']
                if config['ldap']['group_prefix']:
                    filterstr = '(&(objectClass=group)(cn=%s*))' % config['ldap']['group_prefix']
        
        attrlist=['name', 'member']        
        if config['gitlab']['add_description']:
            attrlist.append('description')
        
        for group_dn, group_data in self.l.search_s(base=config['ldap']['groups_base_dn'],
                                                scope=ldap.SCOPE_SUBTREE,
                                                filterstr=filterstr,
                                                attrlist=attrlist):
            logging.info(f"{group_data}")
            ldap_groups_names.append(group_data['name'][0].decode())
            ldap_group = {"name": group_data['name'][0].decode(), "members": []}
            if config['gitlab']['add_description'] and 'description' in group_data:
                ldap_group.update({"description": group_data['description'][0].decode()})
            if 'member' in group_data:
                logger.info("reading members...")
                for member in group_data['member']:
                    member = member.decode()
                    for user_dn, user_data in l.search_s(base=config['ldap']['users_base_dn'],
                                                            scope=ldap.SCOPE_SUBTREE,
                                                            filterstr='(&(|(distinguishedName=%s)(dn=%s))(objectClass=user)%s)' % (
                                                                    member, member, config['ldap']['user_filter']),
                                                            attrlist=['uid', 'sAMAccountName', 'mail', 'displayName']):
                        if 'sAMAccountName' in user_data:
                            username = user_data['sAMAccountName'][0].decode()
                        else:
                            username = user_data['uid'][0].decode()
                        ldap_group['members'].append({
                            'username': username,
                            'name': user_data['displayName'][0].decode(),
                            'identities': str(member).lower(),
                            'email': user_data['mail'][0].decode()
                        })
            ldap_groups.append(ldap_group)
        logging.info('Done.')
        
        return ldap_groups_names



if __name__ == "__main__":
    init()

    ldap_service = LdapService()
    logging.info('Groups currently in LDAP : %s' % str.join(', ', ldap_service.list_groups()))
