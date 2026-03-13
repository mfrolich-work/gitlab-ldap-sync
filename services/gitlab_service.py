import gitlab
import sys
import json
import logging
from dataclasses import dataclass


@dataclass
class GitlabUser:
    username: str
    name: str
    email: str
    identities: str


class GitlabService:

    def __init__(self, config):
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
