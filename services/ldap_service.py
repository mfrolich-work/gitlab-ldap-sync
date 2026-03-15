import sys
import json
import ldap
import ldap.asyncsearch
import logging
from dataclasses import dataclass


@dataclass
class LdapUser:
    username: str
    name: str
    identities: str
    email: str


@dataclass
class LdapGroup:
    name: str
    description: str
    members: list[LdapUser]



class LdapService:

    def __init__(self, config):
        self.l = None

        if not config['ldap']['group_attribute'] and not config['ldap']['group_prefix']:
            self.filterstr = '(objectClass=group)'
        else:
            if config['ldap']['group_attribute'] and config['ldap']['group_prefix']:
                logging.error('You should set "group_attribute" or "group_prefix" but not both in config.json')
                sys.exit(1)
            else:
                if config['ldap']['group_attribute']:
                    self.filterstr = '(&(objectClass=group)(%s=gitlab_sync))' % config['ldap']['group_attribute']
                if config['ldap']['group_prefix']:
                    self.filterstr = '(&(objectClass=group)(cn=%s*))' % config['ldap']['group_prefix']

        self.add_description = config['gitlab']['add_description']
        self.groups_base_dn = config['ldap']['groups_base_dn']
        self.users_base_dn = config['ldap']['users_base_dn']
        self.user_filter = config['ldap']['user_filter']

        if not config['ldap']['url']:
            logging.error('You should configure LDAP in config.json')
            sys.exit(1)

        try:
            self.l = ldap.initialize(uri=config['ldap']['url'])
            self.l.simple_bind_s(config['ldap']['bind_dn'], config['ldap']['password'])
        except Exception as e:
            logging.error("Error while connecting: %s", e)
            sys.exit(1)

    def list_groups(self):
        ldap_groups = []
        
        attrlist=['name', 'member']        
        if self.add_description:
            attrlist.append('description')
        
        for group_dn, group_data in self.l.search_s(base=self.groups_base_dn,
                                                scope=ldap.SCOPE_SUBTREE,
                                                filterstr=self.filterstr,
                                                attrlist=attrlist):
            logging.debug(f"{group_data}")

            ldap_group = LdapGroup(group_data['name'][0].decode(), None, [])
            
            if self.add_description and 'description' in group_data:
                ldap_group.description = group_data['description'][0].decode()
            
            if 'member' in group_data:
                logging.info("reading members...")
                for member in group_data['member']:
                    member = member.decode()
                    for user_dn, user_data in self.l.search_s(base=self.users_base_dn,
                                                            scope=ldap.SCOPE_SUBTREE,
                                                            filterstr='(&(|(distinguishedName=%s)(dn=%s))(objectClass=user)%s)' % (
                                                                    member, member, self.user_filter),
                                                            attrlist=['uid', 'sAMAccountName', 'mail', 'displayName']):
                        if 'sAMAccountName' in user_data:
                            username = user_data['sAMAccountName'][0].decode()
                        else:
                            username = user_data['uid'][0].decode()
                        
                        ldap_group.members.append(LdapUser(username, user_data['displayName'][0].decode(), str(member).lower(), user_data['mail'][0].decode()))

            ldap_groups.append(ldap_group)

        return ldap_groups
