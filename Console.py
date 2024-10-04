import sys
import time
import requests
import curses
import json
import os
import re
import uuid
import maskpass
from typing import List, Tuple, Any
from bs4 import BeautifulSoup, element
import logging
import tempfile


class XiaoYa:
    def __init__(self):
        self.cache = "./account.json"
        self.dialog = requests.Session()
        self.dialog.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
                                                  "like Gecko) Chrome/58.0.3029.110 Safari/537.3"})
        self.video = True
        self.logger = self.gain_logger()

    @staticmethod
    def gain_logger() -> logging.Logger:
        logger = logging.getLogger("xiaoya")
        logger.setLevel("INFO")
        formatter = logging.Formatter("[%(asctime)s]-[%(levelname)s]-%(message)s")
        if not os.path.exists("./log"):
            os.mkdir("./log")
        file_handler = logging.FileHandler(f"./log/{uuid.uuid4()}-xiaoya.log")
        file_handler.setLevel("INFO")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel("INFO")
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        return logger

    @staticmethod
    def cache_decorator(func):
        def wrapper(self, *args, **kwargs):
            if os.path.exists(self.cache):
                with open(self.cache, "r") as f:
                    cache = json.load(f)
                    username, password = cache.get("username"), cache.get("password")
                    return func(self, username, password)
            else:
                self.logger.info("缓存未找到，请手动输入用户名和密码")
                username = input("请输入您的帐号:")
                password = maskpass.askpass(prompt="请输入您的密码：", mask="*")
                with open(self.cache, "w+") as f:
                    json.dump([username, password], f)
                return func(self, username, password)
        return wrapper

    @cache_decorator
    def login(self, u: str, p: str) -> str:
        login_url = ("https://infra.ai-augmented.com/api/auth/cas/login?school_certify=10511&client_id=xy_client_ccnu"
                     "&state=afv340&redirect_uri=https://ccnu.ai-augmented.com/api/jw-starcmooc/user/authorCallback"
                     "&response_type=code&week_no_login_status=0&scope=&next=https://infra.ai-augmented.com/app/auth"
                     "/oauth2/securityNotice?response_type=code&state=afv340&client_id=xy_client_ccnu&redirect_uri"
                     "=https://ccnu.ai-augmented.com/api/jw-starcmooc/user/authorCallback&school=10511&lang=zh_CN"
                     "&back=https://infra.ai-augmented.com/app/auth/oauth2/login?response_type=code&state=afv340"
                     "&client_id=xy_client_ccnu&redirect_uri=https://ccnu.ai-augmented.com/api/jw-starcmooc/user"
                     "/authorCallback&school=10511&lang=zh_CN")
        login_html = self.dialog.get(url=login_url)
        soup = BeautifulSoup(login_html.text, "html.parser")
        login_row = soup.find(class_="row btn-row")
        data = {"username": u, "password": p}
        for login_btn in login_row.children:
            if type(login_btn) == element.NavigableString:
                continue
            if login_btn['name'] == "resetpass":
                continue
            data.update({login_btn["name"]: login_btn["value"]})
        self.dialog.post(url=login_html.url, data=data)
        redirect_url = "https://infra.ai-augmented.com/api/auth/oauth/onAccountAuthRedirect"
        self.dialog.get(url=redirect_url)
        if self.dialog.cookies.get("HS-prd-access-token") is None:
            self.logger.info("登录失败，请检查用户名和密码")
            os.remove(self.cache)
            self.login(u, p, self.dialog)
        else:
            self.logger.info("登录成功")
            return "Bearer " + self.dialog.cookies.get("HS-prd-access-token")

    def get_json(self, url: str) -> bool or dict:
        try:
            response = self.dialog.get(url=url)
            return response.json()
        except Exception as e:
            self.logger.error(e)
            return False

    def get_courses(self, t: int) -> Tuple[List[Any], List[Any]] or bool:
        courses_url = f"https://ccnu.ai-augmented.com/api/jx-iresource/group/student/groups?time_flag={t}"
        data = self.get_json(courses_url)
        if data:
            sources = data.get("data")
            return [i.get("name") for i in sources], [i.get("id") for i in sources]
        else:
            return False

    def download_main(self, cid: str):
        url = "https://ccnu.ai-augmented.com/api/jx-iresource/resource/queryCourseResources?group_id=" + cid
        self.make_root(cid)
        data = self.get_json(url=url)
        file_list = self.data2list(data)
        file_tree = self.list2tree(file_list)
        self.mkdir_download(file_tree)

    def make_root(self, cid: str):
        name = (self.dialog.post(url="https://ccnu.ai-augmented.com/api/jx-iresource/statistics/group/visit",
                                 data={"group_id": cid, "role_type": "normal"}, ).json().get("data").get("name"))
        self.logger.info(f"已创建{os.getcwd()}\\{name}")
        i = 1
        if not os.path.exists("./download"):
            os.mkdir("./download")
        os.chdir("./download")
        while os.path.exists(name):
            if i == 1:
                self.logger.info(f"{name}-路径已存在")
            try:
                self.logger.info(f"将其重名为{name}({i})")
                os.rename(name, f"{name}({i})")
            except Exception as e:
                self.logger.info(f"{name}({i})已存在")
                self.logger.error(e)
                i = i + 1
        os.mkdir(name)
        os.chdir(name)

    @staticmethod
    def data2list(data: dict) -> list:
        return [
            {"id": i.get("id"), "parent_id": i.get("parent_id"), "mimetype": i.get("mimetype"), "name": i.get("name"),
             "type": i.get("type"), "quote_id": i.get("quote_id"), } for i in data.get("data")]

    @staticmethod
    def list2tree(file_list: list) -> dict:
        mapping: dict = dict(zip([i["id"] for i in file_list], file_list))
        file_tree: dict = {}
        for i in file_list:
            parent: dict = mapping.get(i["parent_id"])
            if parent is None:
                file_tree: dict = i
            else:
                children: file_list = parent.get("children")
                if not children:
                    children: file_list = []
                children.append(i)
                parent.update({"children": children})
        return file_tree

    def mkdir_download(self, file_tree: dict) -> None:
        child = file_tree.get("children")
        if not child:
            return None
        for i in child:
            t: str = i.get("type")
            name: str = i.get("name")
            if t == 1:
                os.mkdir(name)
                os.chdir(name)
                self.logger.info(f"已创建{os.getcwd()}\\{name}")
                if i.get("children"):
                    self.mkdir_download(file_tree=i)
                os.chdir("../")
            elif t == 6:
                self.download_wps(item_json=i)
            elif t == 9 and self.video:
                self.download_video(item_json=i)

    def download_wps(self, item_json: dict) -> None:
        quote_id: str = item_json.get("quote_id")
        url: str = ("https://ccnu.ai-augmented.com/api/jx-oresource/cloud/file_url/" + quote_id)
        download_url: str = (self.get_json(url=url).get("data").get("url"))
        with open(item_json.get("name"), "wb+") as f:
            f.write(requests.get(url=download_url).content)
            self.logger.info(f"已下载{os.getcwd()}\\{item_json.get('name')}")

    def download_video(self, item_json: dict) -> None:
        name: str = item_json.get("name")
        try:
            node_id: str = item_json.get("id")
            get_video_id_url: str = (
                    "https://ccnu.ai-augmented.com/api/jx-iresource/resource/queryResource?node_id=" + node_id)
            video_id: str = (self.get_json(get_video_id_url).get("data").get("resource").get("video_id"))
            get_m3u8_url: str = ("https://ccnu.ai-augmented.com/api/jx-oresource/vod/video/play_auth/" + video_id)
            m3u8_url: str = (
                self.get_json(url=get_m3u8_url).get("data").get("private_vod")[0].get("private_url"))
            m3u8_list: str = requests.get(url=m3u8_url).text
            ts_list: list = re.findall(pattern=".*?\.ts", string=m3u8_list)
            with open(name, "ab+") as f:
                for i in ts_list:
                    url: str = "https://vod-trans-1.ccnu.edu.cn" + i
                    f.write(requests.get(url=url).content)
                self.logger.info(f"已下载{os.getcwd()}\\{name}")
        except Exception as e:
            self.logger.info(f"下载{os.getcwd()}\\{name}失败")
            self.logger.error(e)


class Menu:
    @staticmethod
    def print_menu(std: curses.window, selected_row_idx: int, menulist: List[str], t: str):
        std.clear()
        h, w = std.getmaxyx()
        x_title = int(w / 10)
        std.addstr(int(h / 10), x_title, t, curses.A_BOLD)
        for idx, row in enumerate(menulist):
            x = int(w / 10)
            y = int(h / 10) + idx + 2
            if idx == selected_row_idx:
                std.attron(curses.color_pair(1))
                std.addstr(y, x, row)
                std.attroff(curses.color_pair(1))
            else:
                std.attron(curses.color_pair(2))
                std.addstr(y, x, row)
                std.attroff(curses.color_pair(2))
        x = int(w / 10)
        y = int(h - h / 10)
        std.addstr(y, x, "←  前  一 页   →   后 一 页   ↑   上 一 项   ↓   下 一 项 ", curses.A_BOLD)
        std.refresh()

    def menu_selection(self, std: curses.window, menulist: List[str], menu_ids: List[str], t: str) -> str or bool:
        # 分页
        h, w = std.getmaxyx()
        menus_per_page = int(h / 10 * 8 - 4)
        current_page = 0
        current_row = 0
        std.clear()
        curses.curs_set(0)
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
        for i in range(0, len(menulist)):
            menulist[i] = " ".join(list(menulist[i])) + " "
        while True:
            self.print_menu(std, current_row, menulist[current_page * menus_per_page: (current_page + 1) * menus_per_page],
                            t)
            key = std.getch()
            index = current_page * menus_per_page + current_row
            if key == curses.KEY_UP:
                if current_row == 0 and current_page != 0:
                    current_row = min(menus_per_page - 1, len(menulist) - menus_per_page * current_page - 1)
                    current_page = max(0, current_page - 1)
                else:
                    current_row = max(0, current_row - 1)
            elif key == curses.KEY_DOWN:
                if current_row + 1 >= menus_per_page:
                    current_row = 0
                    current_page = min(len(menulist) // menus_per_page, current_page + 1)
                else:
                    current_row = min(min(menus_per_page - 1, current_row + 1), len(menulist) - menus_per_page * current_page - 1)
            elif key == curses.KEY_LEFT:
                current_page = max(0, current_page - 1)
            elif key == curses.KEY_RIGHT:
                current_page = min(len(menulist) // menus_per_page, current_page + 1)
                if current_page * menus_per_page + current_row >= len(menulist):
                    current_row = 0
            elif key == curses.KEY_ENTER or key in [10, 13]:
                return menu_ids[index]
            elif key == 27:
                return False


def welcome():
    text = """
     _  _  ____    __    _____  _  _    __   
    ( \/ )(_  _)  /__\  (  _  )( \/ )  /__\  
     )  (  _)(_  /(__)\  )(_)(  \  /  /(__)\ 
    (_/\_)(____)(__)(__)(_____) (__) (__)(__)

    欢迎使用CCNU小雅课程下载器
    作者：CN-Grace    
    项目主页：https://github.com/CN-Grace/CCNU-xiaoya-DownLoader-py
    觉得好用请来个star⭐吧！
    """
    print(text)


if __name__ == "__main__":
    welcome()
    time.sleep(2)
    client = XiaoYa()
    menu = Menu()
    client.dialog.headers.update({"Authorization": client.login()})
    while True:
        title = "请 选 择 你 要 爬 取 的 课 程 种 类 "
        type_list = ["正在进行", "即将开课", "已结束"]
        id_list = [1, 2, 3]
        type_id = curses.wrapper(menu.menu_selection, type_list, id_list, title)
        if not type_id:
            client.logger.info("感谢使用")
            time.sleep(2)
            sys.exit()
        else:
            name_list, id_list = client.get_courses(t=type_id)
            try:
                check_list = ["是", "否"]
                yes_no = ["Y", "N"]
                if not name_list:
                    client.logger.info("未找到课程")
                    time.sleep(2)
                else:
                    course_title = "请 选 择 你 要 爬 取 的 课 程 名 称 "
                    course_id = curses.wrapper(menu.menu_selection, name_list, id_list, course_title)
                    if not course_id:
                        client.logger.info("感谢使用")
                        time.sleep(2)
                    else:
                        video_title = "是 否 下 载 可 下 载 的 视 频 资 源 "
                        check = curses.wrapper(menu.menu_selection, check_list, yes_no, video_title)
                        if check == "N":
                            client.video = False
                        client.download_main(cid=course_id)
                    check_title = "是 否 继 续 下 载 "
                    check = curses.wrapper(menu.menu_selection, check_list, yes_no, check_title)
                    os.chdir("../")
                    if check == "N":
                        client.logger.info("感谢使用")
                        time.sleep(2)
                        sys.exit()
            except Exception as e:
                client.logger.error(e)
                client.logger.info("下载失败")
                time.sleep(2)
