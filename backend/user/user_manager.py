# coding=utf-8
# author: Lan_zhijiang
# description: 用户管理器
# date: 2020/10/2

import json
from backend.data.encryption import Encryption
from backend.database.mongodb import MongoDBManipulator
from backend.user.user_info_operator import UserInfoManager
from backend.user.user_group_manager import UserGroupManager
from backend.user.user_permission_mamanger import UserPermissionManager


class UserManager:

    def __init__(self, base_abilities):

        self.base_abilities = base_abilities
        self.log = base_abilities.log
        self.setting = base_abilities.setting

        self.mongodb_manipulator = self.base_abilities.mongodb_manipulator
        self.encryption = self.base_abilities.encryption

        # self.encryption = Encryption(log, setting)
        # self.mongodb_manipulator = MongoDBManipulator(log, setting)
        self.user_group_manager = UserGroupManager(self.base_abilities)
        self.user_info_manager = UserInfoManager(self.base_abilities)
        self.user_permission_manager = UserPermissionManager(self.base_abilities)

    def sign_up(self, account, password, email=None, user_group="default"):

        """
        注册用户
        :param account: 账户名
        :param password: 密码(md5)
        :param email: 电子邮箱
        :param user_group: 用户组
        :return bool
        """
        if "/" in account or "." in account or "-" in account:
            self.log.add_log("UserManager: '/', '.' and '-' is banned in account name", 3)
            return False, "account not in law"

        if self.mongodb_manipulator.is_collection_exist("user", account) is True:
            self.log.add_log("UserManager: Sign up fail, this user had already exists. sign up account: " + account, 3)
            return False, "user had already exists"

        if self.mongodb_manipulator.add_collection("user", account) is False:
            self.log.add_log("UserManager: Sign up failed, something wrong while add account. sign up account: " + account, 3)
            return False, "add user went wrong"
        else:
            self.log.add_log("UserManager: Account add to the collection: user successfully", 1)

        # fill user info
        password = self.encryption.md5(password)

        user_info = json.load(open("./backend/data/json/user_info_template.json", "r", encoding="utf-8"))
        user_info[0]["account"] = account
        user_info[1]["password"] = password
        if email is not None:
            user_info[2]["email"].append(email)
        user_info[4]["userGroup"] = user_group

        # update user info into database
        if self.mongodb_manipulator.add_many_documents("user", account, user_info) is False:
            self.log.add_log("UserManager: Sign up failed, something wrong with database, user-%s" % account, 3)
            return False, "database error"
        else:
            # add user into user_group
            res, err = self.user_group_manager.add_users_into_group([account], user_group)
            if res:
                # set user permissions
                user_permissions_list, _ = self.user_permission_manager.get_user_permissions(account, ask_update=True)
                result, _ = self.user_info_manager.update_user_info(account, {"permissionsList": user_permissions_list}, special_allow=True)
                if result is False:
                    self.log.add_log("UserManager: Sign up success but fail to update permissions list", 2)
                    res, err = True, "but fail to update permissions list"
            else:
                self.log.add_log("UserManager: user-%s permissions List load fail because fail to add user into user_group", 3)
                res, err = res, err + ", which means permissions list did not load success"

            # init user's coll-stuff/account
            if self.mongodb_manipulator.add_collection("stuff", account) is False:
                self.log.add_log("UserManager: fail to initialize coll-stuff/%s" % account, 3)
                res, err = False, "fail to init coll-stuff/%s" % account
            else:
                self.log.add_log("UserManager: Initialize coll-stuff/%s success" % account, 1)
                preset_stuff_id_list = json.load(open("./backend/data/json/preset_stuff_id_list.json", "r", encoding="utf-8"))
                self.mongodb_manipulator.add_many_documents("stuff", account, preset_stuff_id_list)

            # init user's coll-classification/account
            if self.mongodb_manipulator.add_collection("classification", account) is False:
                self.log.add_log("UserManager: fail to initialize coll-classification/%s" % account, 3)
                res, err = False, "fail to init coll-classification/%s" % account
            else:
                self.log.add_log("UserManager: Initialize coll-classification/%s success" % account, 1)
                preset_stuff_id_list = json.load(open("./backend/data/json/init_classification.json", "r", encoding="utf-8"))
                self.mongodb_manipulator.add_many_documents("classification", account, preset_stuff_id_list)

            self.log.add_log("UserManager: Sign up user-%s done" % account, 1)
            return res, err

    def delete_user(self, account):

        """
        删除某个用户
        :param account: 账户名
        :return:
        """
        self.log.add_log("UserManager: Delete user: " + account, 1)
        if self.mongodb_manipulator.is_collection_exist("user", account) is False:
            self.log.add_log("UserManager: delete fail, this user does not exists. account: " + account, 1)
            return False, "user does not exists"

        group_name = self.mongodb_manipulator.parse_document_result(
            self.mongodb_manipulator.get_document("user", account, {"userGroup": 1}, 2),
            ["userGroup"]
        )[0]["userGroup"]
        if self.mongodb_manipulator.is_collection_exist("user_group", group_name) is False:
            self.log.add_log("UserManager: fail to delete user-" + account + " because its group-" + group_name +
                             " is not exist", 1)
            return False, "user_group-" + group_name + " is not exist"

        if self.mongodb_manipulator.delete_collection("user", account) is False:
            self.log.add_log("UserGroupManager: delete user-%s fail because of database error" % account, 3)
            return False, "database error"
        else:
            try:
                group_user_list = self.mongodb_manipulator.parse_document_result(
                    self.mongodb_manipulator.get_document("user_group", group_name, {"userList": 1}, 2),
                    ["userList"]
                )[0]["userList"]
                group_user_list.remove(account)
                print(group_user_list)
            except ValueError:
                self.log.add_log("UserManager: success to delete " + "user-" + account + " from user_group-" + group_name +
                                 "because it's not exist at all", 1)
                return True, "user-" + account + " not in the user_group-" + group_name + " at all"

            if self.mongodb_manipulator.update_many_documents("user_group", group_name, {"_id": 1}, {"userList": group_user_list}):
                self.log.add_log("UserManager: delete user-" + account + " success", 1)
                return True, "success"
            else:
                self.log.add_log("UserManager: fail to delete user-" + account + " from user_group-" + group_name +
                                 " because of database error", 3)
                return False, "fail to delete user-" + account + " from user_group-" + group_name

    def login(self, account, password):

        """
        登录
        :param account: 账户
        :param password: 密码
        :return: bool(fail) str(success)
        """
        self.log.add_log("UserManager: Try login " + account, 1)

        user_info, res = self.user_info_manager.get_one_user_multi_info(account, ["password", "avatar"])
        if user_info is False:
            self.log.add_log("UserManager: login: Can't find your account or something wrong in the mongodb "
                             "or user not exist.", 3)
            return False, "database error or user not exist"
        else:
            if self.setting["allowSimultaneousOnline"] is False:
                is_online = self.mongodb_manipulator.parse_document_result(
                    self.mongodb_manipulator.get_document("user", account, {"isOnline": 1}, 2),
                    ["isOnline"]
                )[0]["isOnline"]
                if is_online:
                    self.log.add_log("UserManager: login fail, not allow user simultaneous online", 1)
                    return False, "not allow user simultaneous online"

            if password == user_info["password"]:
                self.mongodb_manipulator.update_many_documents("user", account, {"_id": 14}, {"isOnline": True})

                token = self.encryption.md5(self.log.get_time_stamp() + account)
                last_login_time_stamp = self.log.get_time_stamp()

                self.mongodb_manipulator.update_many_documents("user", account, {"_id": 13}, {"lastLoginTimeStamp": last_login_time_stamp})
                self.mongodb_manipulator.update_many_documents("user", account, {"_id": 7}, {"token": token})
                # self.setting["loginUsers"][account] = {
                #     "account": account,
                #     "lastLoginTimeStamp": last_login_time_stamp,
                #     "avatar": user_info["avatar"] # needs a solution
                # }

                permission_list, err = self.user_permission_manager.get_user_permissions(account, ask_update=True)
                if permission_list is False:
                    self.log.add_log("UserManager: can't get user-" + account + "'s permission list cause: " + err, 3)
                    return False, "permission list can't load"
                # self.setting["loginUsers"][account]["permission"] = permission_list

                self.log.add_log("UserManager: login success", 1)
                return token, "success"
            else:
                self.log.add_log("UserManager: Your password or username is wrong", 1)
                return False, "wrong password or username"

    def logout(self, account):

        """
        登出（竟然给忘了）
        :param account: 要登出的账户名
        :return:
        """
        self.log.add_log("UserManager: Try logout " + account, 1)

        is_online = self.mongodb_manipulator.parse_document_result(
            self.mongodb_manipulator.get_document("user", account, {"isOnline": 1}, 2),
            ["isOnline"]
        )[0]["isOnline"]
        if is_online:
            # del self.setting["loginUsers"][account]
            self.mongodb_manipulator.update_many_documents("user", account, {"token": 1}, {"token": None})

            self.mongodb_manipulator.update_many_documents("user", account, {"_id": 14}, {"isOnline": False})

            self.log.add_log("UserManager: logout success", 1)
            return True, "success"
        else:
            self.log.add_log("UserManager: user: " + account + " have't login yet", 1)
            return False, "user haven't login yet"

