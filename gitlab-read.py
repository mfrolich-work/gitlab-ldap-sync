#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gitlab
import sys
import json
import ldap
import ldap.asyncsearch
import logging
from dataclasses import dataclass


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


@dataclass
class GitlabUser:
    username: str
    name: str
    email: str
    identities: str


class GitlabService:

    def __init__(self):
        self.gl = None
        
        if not config['gitlab']['api']:
            logging.error('GitLab API is empty, aborting.')
            sys.exit(1)
        
        if not config['gitlab']['private_token'] and not config['gitlab']['oauth_token']:
            logging.error('You should set at least one auth information in config.json, aborting.')
        elif config['gitlab']['private_token'] and config['gitlab']['oauth_token']:
            logging.error('You should set at most one auth information in config.json, aborting.')
        else:
            if config['gitlab']['private_token']:
                self.gl = gitlab.Gitlab(url=config['gitlab']['api'], private_token=config['gitlab']['private_token'], ssl_verify=config['gitlab']['ssl_verify'])
            elif config['gitlab']['oauth_token']:
                self.gl = gitlab.Gitlab(url=config['gitlab']['api'], oauth_token=config['gitlab']['oauth_token'], ssl_verify=config['gitlab']['ssl_verify'])
            else:
                self.gl = None
            
            if self.gl is None:
                logging.error('Cannot create gitlab object, aborting.')
                sys.exit(1)

        self.gl.auth()
        logging.info('Done.')

    def list_groups(self):
        logging.info('Getting all groups from GitLab.')
        gitlab_groups = []
        gitlab_groups_names = []

        for group in self.gl.groups.list(all=True):
            gitlab_groups_names.append(group.full_name)
            gitlab_group = {"name": group.full_name, "members": []}
            for member in group.members.list(all=True):
                user = self.gl.users.get(member.id)
                extern_uid = None
                if getattr(user, 'identities', None):
                    if len(user.identities) > 0:
                        extern_uid = user.identities[0].get('extern_uid')

                gitlab_group['members'].append(GitlabUser(user.username, user.name, user.email, extern_uid))
            gitlab_groups.append(gitlab_group)

        logging.info('Done.')
        
        return gitlab_groups




if __name__ == "__main__":
    init()

    gitlab_service = GitlabService()
    groups = gitlab_service.list_groups()
        
    logging.info('Groups currently in Gitlab : %s' % str.join(', ', [group["name"] for group in groups]))

    # extended output        
    for group in groups:
        print(f"Group: {group['name']}")
        for member in group['members']:
            print(f"Member: {member.username}")
