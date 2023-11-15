import asyncio
import json
import os
import re
import sys
import datetime
import hashlib
from flask import request
import webuiapi
from flask import Flask
app = Flask(__name__)
import threading
import requests as requests
import speech_recognition as sr
from markdown import markdown
from nio import AsyncClient, LoginResponse, MatrixRoom, RoomMessageText, InviteMemberEvent, RoomMessageMedia, AsyncClientConfig
import soundfile as sf
import aiofiles.os
import magic
from PIL import Image


signature="ERROR_CouldNotLoadModule"
r = sr.Recognizer()
globalfreeze=False #Удалить
httpchatenabled=False
servicemessages=[]
sendlist=[]
leavelist=[]
picsendlist=[]

#botrtag = "m.notice" # серое
botrtag = "m.text" # не серое сообщение

experimentalenabled=True #Включить экспериментальные функции


#Настройка для запуска тут
with open("settings.txt", "r") as configfile:
    configstr=configfile.readline()
    configstr=configstr.split("%")

    keysstore=configstr[2].split("/") #Токены разделеные /
    user_id=configstr[0] # ID юзера формата @NickOfBot:server.com
    pw=configstr[1] # Пароль
    debugroom=configstr[3] #Отправлять сообщ об ошибке сюда

#Формат файла: В одной строке пишем параметры, пример ниже:
# @NickOfBot:server.com%accountpassword%httptoken1/httptoken2/httptoken3%!debugroomidEQakeDuLIhCE:server.com

sdtest = False
shutdcommand=False
device_name = "FerrumAdapter_1.993"


transcriptcolor="#16E2F5" # Цвет транскрипции (Наркоманский)

#Раз в сколько ждать отсутствие активности чтобы стереть все сообщения
delcounter=360
#Раз в сколько заниматься обслуживанием (хуйней)
maintenancedelay=20


#генерация картинокэ с помощью stable diffusion
sdip="10.0.1.11"
sdport="7860"
sdcolor="#680071" # цвет сообщения о генерации
limitsd=3 #Ограничение stable diffusion множителя разрешения (limitsd-1 = множитель разрешения)


#Загрузить сервисные сообщения в память, те сообщенияф которые надо нахрен удалить
try:
    with open("servicemessages.json", "r") as file:
        servicemessages = json.load(file)
except:
    print("Не смог загрузить список сервисных сообщений :c")


def web(): # запускаем веб сервак чтобы творить дичь по удаленке
    app.run(use_reloader=False, host='0.0.0.0', port=5601)
threading.Thread(target=web).start()



async def drawandsend(text, room, client, hd=1,style="realistic"):
    try:
        hdenabled=True
        tohash = datetime.datetime.now().strftime("%w:%y%S:%f")
        tohash = hashlib.sha256(tohash.encode('UTF-8'))
        tohash = tohash.hexdigest()
        file = tohash
        if sdtest:
            if hd == 1: detailtext = "512x512"; hdenabled = False
            if hd == 2: detailtext = "1024x1024 (Нужно подождать)"
            if hd == 3: detailtext = "1536x1536 (ЭКСПЕРИМЕНТАЛЬНО)"

            if hd == 3: await sendmessage(f"Экспериментальное разрешение. Ты ждун?", room, warning=True, color="#FF0000")
            await sendmessage(f"Пытаюсь нарисовать {text} \nДетализация: {detailtext}\nСтилистика: {style}", room, warning=True, color=sdcolor)

            if style == "realistic": modelstyle="realisticVisionV40_v40VAE.safetensors [e9d3cedc4b]" # пока что тут 2 модели. вставляем сюда свою анимешную и реалистичную.
            if style == "anime": modelstyle = "abyssorangemix3AOM3_aom3a1b.safetensors [5493a0ec49]" # если хотите поменять на другие по смыслу пройдитесь по коду и перепишите !help и !sd команды

            # setup ai img
            apisd = webuiapi.WebUIApi(host=sdip, port=sdport, sampler='DPM++ SDE Karras',steps=20)
            options = {}
            options['sd_model_checkpoint'] = modelstyle
            apisd.set_options(options)
            # END setup ai img

            resultpic = await apisd.txt2img(prompt=text, seed=1337, negative_prompt="ugly, out of frame",cfg_scale=7, use_async=True, enable_hr=hdenabled, hr_scale=hd)
            resultpic.image.save(f"{file}.png")
            await send_image(client, room, f"{file}.png")
            os.remove(f"{file}.png")
        else:
            await sendmessage(f"Не могу нарисовать, сервер отключен :c", room, warning=False, color="#ff0000")
    except Exception as err:
        await sendmessage(f"Не могу нарисовать, сервер подох {err}", room, warning=False, color="#ff0000")


async def send_image(client, room_id, image):
    mime_type = magic.from_file(image, mime=True)  # e.g. "image/jpeg"
    if not mime_type.startswith("image/"):
        print("INVALIDMIME")
    im = Image.open(image)
    (width, height) = im.size
    file_stat = await aiofiles.os.stat(image)
    async with aiofiles.open(image, "r+b") as f:
        resp, maybe_keys = await client.upload(
            f,
            content_type=mime_type,  # image/jpeg
            filename=os.path.basename(image),
            filesize=file_stat.st_size,
        )

    content = {
        "body": os.path.basename(image),  # descriptive title
        "info": {
            "size": file_stat.st_size,
            "mimetype": mime_type,
            "thumbnail_info": None,
            "w": width,  # width in pixel
            "h": height,  # height in pixel
            "thumbnail_url": None,
        },
        "msgtype": "m.image",
        "url": resp.content_uri,
    }

    try:
        await client.room_send(room_id, message_type="m.room.message", content=content)
    except Exception:
        print("ENDPNGSENDEXCEPT")



async def sdscanner():
    while True:
        global sdtest
        try:
            requests.get(f"http://{sdip}:{sdport}", timeout=1)
            sdtest=True
            await asyncio.sleep(60)
        except:
            sdtest=False
            await asyncio.sleep(60)


async def sendtask():
    #Отправка сообщений и картинок которые запланировано отправить через http запросы /send и /send_picture
    #todo Добавить try
    while True:
        await asyncio.sleep(2)
        while len(sendlist) > 0:
            await asyncio.sleep(1)
            item=sendlist.pop()
            item=item.split("%")
            if len(item)==3 or len(item)==4:
                if item[2] == "True":
                    warning=True
                else:
                    warning=False
                await sendmessage(item[0], item[1], warning, color=item[3])

        while len(picsendlist) > 0:
            await asyncio.sleep(1)
            item=picsendlist.pop() #room%path
            item=item.split("%")
            if len(item) == 2:
                roomid=item[0]
                path=item[1]
                await send_image(client, roomid, path)


def get_file_hash(filename):
    try:
       h = hashlib.sha1()
       with open(filename,'rb') as file:
           chunk = 0
           while chunk != b'':
               chunk = file.read(1024)
               h.update(chunk)
       return h.hexdigest()
    except:
        return "CHECK_FAILED"


async def leavetask():
    while True:
        await asyncio.sleep(10)
        while len(leavelist) > 0:
            await asyncio.sleep(1)
            leave=leavelist.pop()
            await client.room_leave(leave)
            await client.room_forget(leave)




# Блядский вебсервер
@app.route("/shutdown")
async def shutdown():
    global shutdcommand
    token=None
    token = request.args.get('token')
    if await checktoken(token):
        response_data = {
            'errcode': 'OK',
        }
        shutdcommand=True
        return response_data, 200
    else:
        response_data = {
            'errcode': 'Token_Invalid'}
        return response_data, 401


@app.route("/status")
async def status():
    token=None
    token = request.args.get('token')
    if await checktoken(token):
        response_data = {
            'errcode': 'OK',
            'freeze': str(globalfreeze),
            'send_lenght': len(sendlist),
            'leave_lenght': len(leavelist),
            'servicemessages_lenght': len(servicemessages)
        }
        return response_data, 200
    else:
        response_data = {
            'errcode': 'Token_Invalid'}
        return response_data, 401

@app.route("/send")
async def send_message():
    global sendlist

    #токен авторизации
    token = request.args.get('token')
    color = request.args.get('color')
    if color == None:
        color = "#808080"
    message = request.args.get('message')
    room_id = request.args.get('room_id')
    warning=False # как сука оно работает?
    warning = request.args.get('warning')

    #Проверка кучи условий на предмет хуйни
    if await checktoken(token):
        if not message == None and not room_id == None and not warning==None:
            response_data = {
                'errcode': 'OK',
                'status': 'Added_To_Tasker'}
            sendlist.append(f"{message}%{room_id}%{warning}%{color}")

            return response_data, 200
        else:
            response_data = {
                'errcode': 'Invalid_Parameters',
                'status': 'error'}
            return response_data, 400
    else:
        response_data = {
            'errcode': 'TOKEN_INVALID'}
        return response_data, 401




@app.route("/send_pic")
#TODO починить, тут нужно получать по HTTP картинку, так лучше. Пока что нужно локальный path до картинки
#Можно добавить warning как в /send
async def send_pic():
    global sendlist
    global picsendlist

    #токен авторизации
    token = request.args.get('token')
    path = request.args.get('path')
    room_id = request.args.get('room_id')

    #Проверка кучи условий на предмет хуйни
    if await checktoken(token):
        if not room_id == None and not path==None:
            response_data = {
                'errcode': 'OK',
                'status': 'Added_To_Tasker'}
            picsendlist.append(f"{room_id}%{path}")

            return response_data, 200
        else:
            response_data = {
                'errcode': 'Invalid_Parameters',
                'status': 'error'}
            return response_data, 400
    else:
        response_data = {
            'errcode': 'TOKEN_INVALID'}
        return response_data, 401


@app.route("/leave")
async def leave():
    #global client
    #токен авторизации
    token=None
    token = request.args.get('token')

    #ID комнаты
    room_id = None
    room_id = request.args.get('room_id')

    #Проверка кучи условий на предмет хуйни
    if await checktoken(token):
        if not room_id == None:
            leavelist.append(room_id)
            response_data = {
                    'errcode': 'OK',
                    'status': 'Left_successfully'}
            return response_data, 200
        else:
            response_data = {
                'errcode': 'Invalid_Parameters',
                'status': 'error'}
            return response_data, 400
    else:
        response_data = {
            'errcode': 'TOKEN_INVALID'}
        return response_data, 401



async def checktoken(token):
    if token in keysstore:
        return True
    else:
        return False


async def setdisplayname(displayname):
    global client
    await client.set_displayname(displayname)


async def autodelete():
    #автоматически удалять сообщения если нет активности (если отмечено, либо юзерские команды)
    global delcounter
    global servicemessages
    global counter
    counter = delcounter
    while True:
        await asyncio.sleep(1)
        counter = counter-1
        while counter<1 or len(servicemessages)>10:
            await asyncio.sleep(2)
            if len(servicemessages) > 0:
                eventd=servicemessages.pop(0)
                eventd=eventd.split("%")
                await redact(eventd[0], eventd[1], "Служба автоочистки соообщений")
                print(f"deleting data {eventd[0]} {eventd[1]}")
                if len(servicemessages)<1:
                    counter=delcounter
            else:
                counter = delcounter





async def launchtimer(): #УДАЛИТЬ
    # .synched() или типо того
    global globalfreeze
    print("1 сек до разморозки")
    await asyncio.sleep(1)
    print("Выхожу из заморозки")
    globalfreeze=False

def write_details_to_disk(resp: LoginResponse, homeserver) -> None:
    with open("credentials.json", "w") as f:
        json.dump(
            {
                "homeserver": homeserver,  # e.g. "https://matrix.example.org"
                "user_id": resp.user_id,  # e.g. "@user:example.org"
                "device_id": resp.device_id,  # device ID, 10 uppercase letters
                "access_token": resp.access_token,  # cryptogr. access token
            },f,)

async def reporterror(error):
    print(f"[ОТПАРВЛЕНО СООБЩЕНИЕ ОБ ОШИБКЕ] {error}")
    await sendmessage(f"[{datetime.datetime.now()}] {error}", debugroom)



async def invite(self, room: MatrixRoom) -> None:
    try:
       await client.join(self.machine_name)
       print(f"Вошел: {self.machine_name}")
       #await sendmessage("Если вы готовы дать мне разрешение на работу в этой комнате\nНапишите !enable\nВ обратном случае ваши сообщения и любые логи не будут сохранены\nНапишите !freeze чтобы отключить для этой комнаты\nВсе что выше не работает, не пытайтесь", room.room_id)
    except:
       await reporterror(f"Не смог войти в комнату {self.machine_name}")


async def audiocallback(room: MatrixRoom, event: RoomMessageMedia) -> None:
    # Мерзкий голосок в кошерный текст
    if not globalfreeze:
        try:
            responsev=await client.download(event.url)

            with open("voice.ogg", "wb") as binary_file:
                binary_file.write(responsev.body)

            data, samplerate = sf.read('voice.ogg')
            sf.write('voice.wav', data, samplerate)

            with sr.AudioFile("voice.wav") as source:
                audio_data = r.record(source)
                text = r.recognize_google(audio_data, language="ru-RU") # дада сраная компания зла.
                await sendmessage(f"Транскрипция(BETA):\n{text}", room.room_id, True, color=transcriptcolor)
            os.remove("voice.ogg")
            os.remove("voice.wav")
            print("Создал транскрипцию")
        except:
            print("Ошибка транскрипции") # ебучие картинки не обрабатывать!


async def checkpoint():
    #Обновить файл где хранятся данные сообщений который планируем удалить.
    with open("servicemessages.json", "w") as file:
        json.dump(servicemessages, file)
async def shutdown():
    # Дописать
    print("Saving data and exiting")
    await checkpoint()
    quit()


async def trust_devices(self, user_id: str,device_list = None) -> None:
       # Спиздил с доков
        """Trusts the devices of a user.

        If no device_list is provided, all of the users devices are trusted. If
        one is provided, only the devices with IDs in that list are trusted.

        Arguments:
            user_id {str} -- the user ID whose devices should be trusted.

        Keyword Arguments:
            device_list {Optional[str]} -- The full list of device IDs to trust
                from that user (default: {None})
        """

        print(f"{user_id}'s device store: {self.device_store[user_id]}")

        # The device store contains a dictionary of device IDs and known
        # OlmDevices for all users that share a room with us, including us.

        # We can only run this after a first sync. We have to populate our
        # device store and that requires syncing with the server.
        for device_id, olm_device in self.device_store[user_id].items():
            if device_list and device_id not in device_list:
                # a list of trusted devices was provided, but this ID is not in
                # that list. That's an issue.
                print(
                    f"Not trusting {device_id} as it's not in {user_id}'s pre-approved list."
                )
                continue

            if user_id == self.user_id and device_id == self.device_id:
                # We cannot explicitly trust the device @alice is using
                continue

            self.verify_device(olm_device)
            print(f"Trusting {device_id} from user {user_id}")



async def messageprepare(question, displayusername, responseuserid, userid, responsebuilder, room, event, client):
    try:
        if len(responsebuilder) == 3:
            answer = responsebuilder[0]
            answer = re.sub(r'<([^>]+)>', '', answer)
            answer = answer[1:]
            answer = answer.strip()
        else:
            answer = None
        question = question.strip()
        if question.startswith("!"):
            servicemessages.append(f"{event.event_id}%{room.room_id}")
            #В плкйсхолдере не displayusername
        if httpchatenabled:
            response = await sendtocore(question, userid, room.room_id, answer, room.user_name(event.sender), event.event_id, "DISPNAME_PLACEHOLDER_RESP", responseuserid, "EventIdReplyPlaceholder")
            if not response == None:
                if response[:3] not in ['err', 'wrn', 'log', 'dbg']:
                        await sendmessage(response, room.room_id,warning=False)
    except Exception as err:
        await reporterror(f"Ошибка CallBack.\nВсе плохо ({err})")


async def message_callback(room: MatrixRoom, event: RoomMessageText) -> None:
    #Код хуилы, переписать
    global response
    if not globalfreeze:
        await client.room_read_markers(room_id=room.room_id, fully_read_event=event.event_id, read_event=event.event_id)
        #await client.room_typing(room_id=room.room_id,typing_state=True, timeout=3000) # тайпер заебал, нахуй его
        #Вытаскиваем из списков нужное для answer и question


        #Шифрование ПОФИКСИТЬ! Дичайший костыль
        asyncio.get_event_loop().create_task(trust_devices(client, user_id=event.sender))


        if not event.sender == user_id:
            responsebuilder=event.source['content']
            responsebuilder=responsebuilder['body']
            responsebuilder=responsebuilder.split("\n")
            if len(responsebuilder)==3:
                question=responsebuilder[2]
            elif len(responsebuilder)==1:
                question = responsebuilder[0]
            else:
                await reporterror("Неопознаный массив с ответом/вопросом") #пофиксить
                question="None"
            displayusername=room.user_name(event.sender)

            #Выдернуть из хуйни юзернейм на который отвечают
            try:
                responseuserid=event.body.split("\n")
                responseuserid=responseuserid[0]
                responseuserid=re.search(r"<(.*?)>", responseuserid).group(1)
            except:
                responseuserid="None"
            userid=event.source["sender"]

            #Проверяем локальную команду, иначе в ядрою ПЕРЕПИСАТ ПАРАШУ
            cmdresp, cmdbool= await localcmdproc(message=question,userid=userid, roomid=room.room_id)

            if cmdbool:
                servicemessages.append(f"{event.event_id}%{room.room_id}")
                await sendmessage(cmdresp,room.room_id,False)
            else:
                await messageprepare(question, displayusername, responseuserid, userid, responsebuilder,room,event,client)
    else:
        print("Адаптер заморожен, игнорирую")





async def sendmessage(message, room_id, warning=True, color="#808080"):
    global counter
    response_s=await client.room_send(
        room_id,
        message_type="m.room.message",
        content={"msgtype": botrtag, "body": message, "format": "org.matrix.custom.html", "formatted_body": markdown(f'<font color="{color}">{message}</font>', extensions=['nl2br'])})
    if not warning:
        response_s = str(response_s)
        start_index = response_s.find("event_id='") + len("event_id='")
        end_index = response_s.find("'", start_index)
        event_id = response_s[start_index:end_index]
        servicemessages.append(f"{event_id}%{room_id}")
        #Ресет таймера удаления
        counter=delcounter



async def redact(event_id, room_id, reason="Автоматическое модерирование"):
    try:
        await client.room_redact(room_id=room_id, event_id=event_id, reason=reason)
    except:
        await reporterror("Не удалось стереть сообщение")
        pass


async def maintenance():
    #параша, не работает, автовыход из пустых комнат и прочие приколы
    while True:
        await asyncio.sleep(maintenancedelay)
        print("Начинаю обслуживание")
        for i in client.rooms:
            print(i)
            print(i.joined_count)
        try:
            os.remove("voice.ogg")
        except:
            pass
        try:
            os.remove("voice.wav")
        except:
            pass
        print("Обслуживание закончено")





async def testmode():
    #Код для тестов, не юзать
    print("Режим тестирования через 10 секунд")
    await asyncio.sleep(10)
    print("Тестирование")
    await sendmessage("**testmessage**", "!eNNjcxTqrfHeuyUiTj:advancedsoft.mooo.com")
    await sendmessage("line1\nline2\nline3", "!eNNjcxTqrfHeuyUiTj:advancedsoft.mooo.com")



async def main() -> None:
    global signature
    # Асинк нахуй не нужон
    try:
        signature=get_file_hash("main.py")
    finally:
        pass

    #Запуск тасков
    asyncio.get_event_loop().create_task(sendtask()) #Такск отправки сообщений (http server)
    asyncio.get_event_loop().create_task(leavetask())  # Таск выхода
    asyncio.get_event_loop().create_task(launchtimer()) #Таск Разморозки удалить нахуй
    asyncio.get_event_loop().create_task(autodelete()) # Таск автоудаления сообщений, не отключать
    asyncio.get_event_loop().create_task(sdscanner()) #SD Проверка коннекта


    #asyncio.get_event_loop().create_task(testmode()) #Таск автотеста для диагостики, бесит параша
    #asyncio.get_event_loop().create_task(maintenance()) #Таск обслуживания
    # веб сервант, КАКОЙ ФИКУС


    global client

    client_config = AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=True)


    if not os.path.exists("credentials.json"):
        homeserver = "https://advancedsoft.mooo.com"
        if not (homeserver.startswith("https://") or homeserver.startswith("http://")):
            homeserver = "https://" + homeserver
        client = AsyncClient(homeserver, user_id,config=client_config)
        resp = await client.login(pw, device_name=device_name)
        if isinstance(resp, LoginResponse):
            write_details_to_disk(resp, homeserver)
            print("Пожулайста перезапусти меня!!")

        else:
            print(f'homeserver = "{homeserver}"; user = "{user_id}"')
            print(f"Failed to log in: {resp}")
            sys.exit(0)

    else:
        with open("credentials.json", "r") as f:
            config = json.load(f)
            client = AsyncClient(config["homeserver"])
            client.access_token = config["access_token"]
            client.user_id = config["user_id"]
            client.device_id = config["device_id"]
            client.store_path="storage"
            client.load_store()
            client.add_event_callback(message_callback, RoomMessageText)
            client.add_event_callback(invite, InviteMemberEvent)
            client.add_event_callback(audiocallback, RoomMessageMedia)

            await client.sync_forever(timeout=30000, full_state=True)


async def experimentalcommandexec(message,userid,roomid=None):
    #Экмпериментальные тестовые команды, отключите experimentalenabled!
    global limitsd
    global counter
    global httpchatenabled
    global experimentalenabled
    if experimentalenabled:
        try:
            message=message.split()
            while len(message) < 6: message.append(" ")
            if message[0]=="!ex":
                if message[1]=="sdres3":
                    if message[2]==0:
                        limitsd=3
                        await sendmessage("[EX] sdlimit вкл", roomid, color="#00FF64")
                    else:
                        limitsd=4
                        await sendmessage("[EX] sdlimit отключен (ОСТОРОЖНО)", roomid, color="#00FF64")
                elif message[1]=="clear":
                    counter=0
                    await sendmessage("[EX] Выполняю очистку", roomid, warning=True, color="#00FF64") #оставляет мерзкое сообщение
                elif message[1]=="checkpoint":
                    await checkpoint()
                    await sendmessage("[EX] Создаю чекпоинт сервисных данных", roomid, warning=False, color="#00FF64")
                elif message[1]=="core":
                    if message[2] == 0:
                        httpchatenabled=False
                        await sendmessage("[EX] Отключено от ядра", roomid, warning=False,
                                          color="#00FF64")
                    else:
                        httpchatenabled = True
                        await sendmessage("[EX] Подключено к ядру", roomid, warning=False,
                                          color="#00FF64")
                elif message[1]=="exlock":
                    if message[2]==1:
                        experimentalenabled=False
                        await sendmessage("[EX] Экспериментальные функции отключены до перезапуска", roomid, warning=False,
                                          color="#00FF64")
        except:
            await sendmessage("[EX] Сбой настройки", roomid, color="#FF0000")
    else:
        await sendmessage("[EX] Экспериментальный режим отключен", roomid, color="#FF0000")



async def localcmdproc(message, userid, roomid=None):
    # инвалидные команды
    try:
        await experimentalcommandexec(message,userid,roomid) # Экспериментальные команды
        global globalfreeze
        cmdresp = None
        cmdbool = False
        if message.startswith("!"):
            if message == "!lhelp":
                cmdresp="*В разработке*\n!lver - Версия адаптера \n!sd (Детализация: от 1 до 2) (Стилистика: anime или realistic) (Запрос) - Запрос картинки с stable diffusion (BETA) только на английском. \n!info - Информация о боте-адаптере"
                cmdbool=True
            elif message.startswith("!sd"):
                cmdbool = True
                message=message.split(" ")
                if len(message)>3:
                    if message[1].isnumeric() and int(message[1]) < limitsd and int(message[1]) > 0:
                        if message[2] == "realistic" or message[2]=="anime":
                            style=message[2]
                            detail=message[1]
                            #rebuild
                            request = ""
                            message.pop(0)
                            message.pop(0)
                            message.pop(0)
                            for i in message:
                                request += str(i)
                                request += ' '
                            asyncio.get_event_loop().create_task(drawandsend(text=request, room=roomid, client=client, hd=int(detail), style=style))
                        else:
                            cmdresp = "Кажется ты что то не так написал (Не хватает аргументов)\nФормат: !sd (Детализация от 1 до 2) (Стилистика: anime или realistic) (Запрос)"
                    else:
                        cmdresp="Кажется ты что то не так написал (Неверный уровень детализации)\nФормат: !sd (Детализация от 1 до 2) (Стилистика: anime или realistic) (Запрос)"
                else:
                    cmdresp = "Кажется ты что то не так написал (Неверный стиль)\nФормат: !sd (Детализация от 1 до 2) (Стилистика: anime или realistic) (Запрос)"

            elif message == "!lver":
                cmdresp=f"Версия адаптера: {device_name}\nСигнатура файла адаптера: {signature}"
                cmdbool=True
            elif message == "!info":
                cmdbool = True
                cmdresp=f"Сигнатура файла адаптера: {signature} \nСоединение SD: {sdtest}\nВерсия адаптера: {device_name}"
            elif message == "!cleanup":
                pass
        return [cmdresp,cmdbool]
    except Exception as err:
        print(f"CMD_ERROR_OCCURED {err}")
        return ["err", False]



# answer ответ
# question сообщение
async def sendtocore(question, userid, roomid, answer, username, message_id, reply_user_name, reply_user_id, reply_message_id):
    #Отправка ядру на обработку соообщения и возврат ответа, если нет ядра, чек строку 412
    global response
    global globalfreeze
    try:
        request = requests.get(f'http://127.0.0.1:5555/get_answer',
                                params={'text': question,
                                        'message_id': message_id,
                                        'user_id': userid,
                                        'user_name': username,
                                        'chat_id': roomid,
                                        'reply_text': answer,
                                        'reply_message_id': reply_message_id,
                                        'reply_user_id': reply_user_id,
                                        'reply_user_name': reply_user_name,
                                        'reply_chat_id': roomid,
                                        'api': 'matrix'})
        response = request.text


        if not request.status_code ==200:
            await reporterror(f"Ошибка ядра httpcode:{request.status_code} text: {request.text}")
            response="dbg: core_failed(fromAdapter)"
        return response
    except:
        await reporterror("Ядро ferrum недоступно по HTTP, замораживаю адаптер")
        globalfreeze = True
        return "Ошибка ядра, извините."
asyncio.run(main())
