#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gitlab
import sys
import json
import ldap
import ldap.asyncsearch
import logging
import urllib3
import re
from services.gitlab_service import GitlabService
from services.gitlab_service import GitlabGroup
from services.ldap_service import LdapService

config = None

def init():
    global config

    print('Initializing.')
    
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


def parse_group_name(s: str):
    prefix = "g.Gitlab02-"
    
    if not s.startswith(prefix):
        return (None, None)
    
    rest = s[len(prefix):]
    project, _, role = rest.rpartition("-")
    
    return project, role


if __name__ == "__main__":
    init()

    logging.info('Connecting to GitLab')
    gitlab_service = GitlabService(config)
    ldap_service = LdapService(config)

    logging.info('Getting all groups from GitLab.')
    gitlab_groups = gitlab_service.list_groups()
    logging.info('Done.')

    logging.info('Getting all groups from LDAP.')
    ldap_groups = ldap_service.list_groups()
    logging.info('Done.')

    gitlab_groups_names = [g.name for g in gitlab_groups]
    ldap_groups_names = [g.name for g in ldap_groups]

    logging.info('Groups currently in GitLab : %s' % str.join(', ', gitlab_groups_names))
    logging.info('Groups currently in LDAP : %s' % str.join(', ', ldap_groups_names))
            
    logging.info('Syncing Groups from LDAP.')

    for ldap_group in ldap_groups:
        logging.info('Working on group %s ...' % ldap_group.name)
        
        gitlab_name, gitlab_role = parse_group_name(ldap_group.name)
        logging.info('Extracted name: %s, role: %s', gitlab_name, gitlab_role)

        if not gitlab_name or not gitlab_role:
            logging.info('|- Project or role couldn\'t be extracted from LDAP group')
            continue
        
        gitlab_group = next((g for g in gitlab_groups if g.name == gitlab_name), None)
        if not gitlab_group:
            
            logging.info('|- Group not existing in GitLab, creating.')
            new_gitlab_group = {'name': gitlab_name, 'path': gitlab_name, 'visibility': config['gitlab']['group_visibility']}
            
            if config['gitlab']['add_description'] and ldap_group.description is not None:
                new_gitlab_group.update({'description': ldap_group.description})
            
            try:
                description_optional = ldap_group.description if config['gitlab']['add_description'] else None
                gitlab_service.create_group(gitlab_name, gitlab_name, config['gitlab']['group_visibility'], description_optional)

                gitlab_group = GitlabGroup.from_ldap_group(ldap_group)
                gitlab_groups.append(gitlab_group)
            except Exception as e:
                logging.error('Creating group %s failed: %s' % (ldap_group.name, e))
                # Skip next steps due to group could not be created
                continue
        else:
            logging.info('|- Group already exist in GitLab, skiping creation.')

        logging.info('|- Working on group\'s members.')

        for ldap_member in ldap_group.members:

            gitlab_member = next((m for m in gitlab_group.members if m.email.lower() == ldap_member.email.lower()), None)        
            
            if not gitlab_member:
                logging.info('|  |- User %s is member in LDAP but not in GitLab, updating GitLab.', ldap_member.email)
                gitlab_service.add_member(gitlab_group.name, ldap_member.email.lower(), gitlab_role)
            else:
                if gitlab_service.compare_roles(gitlab_role, gitlab_member.role) > 0:
                    logging.info('|  |- User %s already in gitlab group, updating role %s -> %s.', ldap_member.email, gitlab_member.role, gitlab_role)    
                    gitlab_service.remove_member(gitlab_group.name, ldap_member.email.lower())
                    gitlab_service.add_member(gitlab_group.name, ldap_member.email.lower(), gitlab_role)
                else:
                    logging.info('|  |- User %s already in gitlab group, skipping.' % ldap_member.email)

        logging.info('Done.')
        continue




        logging.info('Cleaning membership of LDAP Groups')

        for g_group in gitlab_groups:
            logging.info('Working on group %s ...' % g_group['name'])
            if g_group['name'] in ldap_groups_names:
                logging.info('|- Working on group\'s members.')
                for g_member in g_group['members']:
                    if g_member not in ldap_groups[ldap_groups_names.index(g_group['name'])]['members']:
                        if str(config['ldap']['users_base_dn']).lower() not in g_member['identities']:
                            logging.info('|  |- Not a LDAP user, skipping.')
                        else:
                            logging.info('|  |- User %s no longer in LDAP Group, removing.' % g_member['name'])
                            g = [group for group in gl.groups.list(search=g_group['name']) if group.name == g_group['name']][0]
                            u = gl.users.list(username=g_member['username'])[0]
                            if u is not None:
                                g.members.delete(u.id)
                                g.save()
                    else:
                        logging.info('|  |- User %s still in LDAP Group, skipping.' % g_member['name'])
                logging.info('|- Done.')
            else:
                logging.info('|- Not a LDAP group, skipping.')
            logging.info('Done')
