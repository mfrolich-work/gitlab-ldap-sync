import gitlab
import sys
import json
import logging
from gitlab import const
from dataclasses import dataclass
from services.ldap_service import LdapGroup
from services.ldap_service import LdapUser


@dataclass
class GitlabUser:
    username: str
    name: str
    email: str
    identities: str
    role: str

    @staticmethod
    def from_ldap_user(ldap_user: LdapUser):
        return GitlabUser(ldap_user.username, ldap_user.name, ldap_user.email, ldap_user.identities, None)


@dataclass
class GitlabGroup:
    name: str
    members: list[GitlabUser]

    @staticmethod
    def from_ldap_group(ldap_group: LdapGroup):
        new_group = GitlabGroup(ldap_group.name, [])
#        for member in ldap_group.members:
#            new_group.members.append(GitlabUser.from_ldap_user(member))

        return new_group


class GitlabService:

    ROLE_MAP_NUM = {
        10: "guest",
        20: "reporter",
        30: "developer",
        40: "maintainer",
        50: "owner",
    }

    ROLE_MAP_STR = {
        "guest": 10,
        "reporter": 20,
        "developer": 30,
        "maintainer": 40,
        "owner": 50,
    }

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


    def list_groups(self):
        gitlab_groups = []

        for group in self.gl.groups.list(all=True):

            gitlab_group = GitlabGroup(group.full_name, [])
            logging.debug(f"Reading members of {gitlab_group.name}")
            for member in group.members.list(all=True):
                user = self.gl.users.get(member.id)
                logging.debug(f"Member: {member}")

                extern_uid = None
                if getattr(user, 'identities', None):
                    if len(user.identities) > 0:
                        extern_uid = user.identities[0].get('extern_uid')

                role = self.ROLE_MAP_NUM.get(getattr(member, "access_level", None))
                gitlab_group.members.append(GitlabUser(user.username, user.name, user.email, extern_uid, role))

            gitlab_groups.append(gitlab_group)
        
        return gitlab_groups

    def create_group(self, name, path, visibility, description):
        new_gitlab_group = {'name': name, 'path': path, 'visibility': visibility}
        
        if description is not None:
            new_gitlab_group.update({'description': description})
        
        g = self.gl.groups.create(new_gitlab_group)
        g.save()

    def get_user_by_email(self, email):
        users = self.gl.users.list(search=email)
        
        if len(users) == 0:
            return None

        filtered = [user for user in users if user.email.lower() == email.lower()]
        if len(filtered) > 0:
            return filtered[0]

        return None

    def add_member(self, group_name, email, role):
        
        g = [group for group in self.gl.groups.list(search=group_name) if group.name == group_name][0]
        g.save()
        u = self.get_user_by_email(email)
        
        if u:
            if u not in g.members.list(all=True):

                role = role.lower()
                gitlab_role = self.ROLE_MAP_STR.get(role)
                if gitlab_role is not None:
                    g.members.create({'user_id': u.id, 'access_level': gitlab_role})
                    logging.info('|  |- User %s added to group %s.', email, group_name)
                else:
                    logging.info('|  |- Unknown role: %s, skipping.', role)        
            
                logging.info('|  |- User %s removed from group %s.', email, group_name)
        else:
            logging.info('|  |- User %s does not exist in gitlab, skipping.', email)


    def remove_member(self, group_name, email):
        
        g = [group for group in self.gl.groups.list(search=group_name) if group.name == group_name][0]
        g.save()
        u = self.get_user_by_email(email)
        
        if u:
            members = g.members.list(all=True)
            member = next((m for m in members if m.id == u.id), None)

            if member:
                g.members.delete(member.id)
                logging.info('|  |- User %s removed from group %s.', email, group_name)
            else:
                logging.info('|  |- User %s is not a member of group %s.', email, group_name)
            
        else:
            logging.info('|  |- User %s does not exist in gitlab, skipping.', email)


    def compare_roles(self, role1, role2):
        num1 = self.ROLE_MAP_STR.get(role1)
        num2 = self.ROLE_MAP_STR.get(role2)

        if num1 is None or num2 is None:
            return None
                
        return (num1 > num2) - (num1 < num2)
