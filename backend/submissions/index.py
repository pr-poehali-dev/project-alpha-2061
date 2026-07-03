import json
import os
import base64
import uuid
import re
import urllib.request
import psycopg2
import boto3


def upload_bytes(s3, bucket_cdn_id, key, data, content_type):
    s3.put_object(Bucket='files', Key=key, Body=data, ContentType=content_type)
    return f'https://cdn.poehali.dev/projects/{bucket_cdn_id}/bucket/{key}'


def call_mistral(messages, response_format_json=True):
    api_key = os.environ['MISTRAL_API_KEY']
    payload = {
        'model': 'mistral-large-latest',
        'messages': messages,
        'temperature': 0.7
    }
    if response_format_json:
        payload['response_format'] = {'type': 'json_object'}

    req = urllib.request.Request(
        'https://api.mistral.ai/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    return result['choices'][0]['message']['content']


def send_telegram_message(chat_id, text):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token or not chat_id:
        return
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data=json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass


def handler(event: dict, context) -> dict:
    '''Приём заявок на генерацию КП, ИИ-обработка референса и старого КП, редактирование и отправка результата в Telegram'''
    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id, X-Auth-Token, X-Session-Id',
                'Access-Control-Max-Age': '86400'
            },
            'body': ''
        }

    headers = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'application/json'
    }

    dsn = os.environ['DATABASE_URL']
    schema = os.environ['MAIN_DB_SCHEMA']
    params = event.get('queryStringParameters') or {}
    action = params.get('action', '')

    s3 = boto3.client(
        's3',
        endpoint_url='https://bucket.poehali.dev',
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
    )
    bucket_cdn_id = os.environ['AWS_ACCESS_KEY_ID']

    if method == 'POST' and action == 'get_upload_url':
        body = json.loads(event.get('body', '{}'))
        filename = body.get('filename', 'file.pdf')
        prefix = body.get('prefix', 'file')
        content_type = body.get('content_type', 'application/octet-stream')

        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        key = f'submissions/{uuid.uuid4()}/{prefix}_{safe_name}'

        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={'Bucket': 'files', 'Key': key, 'ContentType': content_type},
            ExpiresIn=600
        )
        cdn_url = f'https://cdn.poehali.dev/projects/{bucket_cdn_id}/bucket/{key}'

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'upload_url': upload_url, 'cdn_url': cdn_url, 'filename': safe_name})
        }

    if method == 'POST' and action == 'generate':
        body = json.loads(event.get('body', '{}'))
        name = body.get('name', '').strip()
        telegram_contact = body.get('telegram_contact', '').strip()
        old_kp_url = body.get('old_kp_url', '').strip()
        old_kp_filename = body.get('old_kp_filename', 'file.pdf')
        reference_kp_url = body.get('reference_kp_url', '').strip()
        reference_kp_filename = body.get('reference_kp_filename', 'file.pdf')

        if not name or not telegram_contact or not old_kp_url or not reference_kp_url:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Заполните имя, телеграм и загрузите оба файла'})
            }

        old_kp_text = body.get('old_kp_text', '')[:6000]

        ai_messages = [
            {
                'role': 'system',
                'content': (
                    'Ты дизайнер и копирайтер коммерческих предложений. '
                    'Тебе дают текст старого КП клиента и описание референса дизайна, который клиенту нравится. '
                    'Твоя задача — собрать структуру нового красивого КП: заголовок, подзаголовок, '
                    'список блоков (title, description), палитру из 3 HEX-цветов (primary, secondary, accent), '
                    'и рекомендацию по шрифту (google font name). '
                    'Ответь строго в формате JSON: '
                    '{"title": "", "subtitle": "", "sections": [{"title": "", "description": ""}], '
                    '"colors": {"primary": "#xxxxxx", "secondary": "#xxxxxx", "accent": "#xxxxxx"}, "font": ""}'
                )
            },
            {
                'role': 'user',
                'content': (
                    f'Текст старого КП клиента:\n{old_kp_text}\n\n'
                    f'Название референса дизайна (файл): {reference_kp_filename}. '
                    'Ориентируйся на премиальный, современный корпоративный стиль.'
                )
            }
        ]

        try:
            ai_response = call_mistral(ai_messages)
            generated = json.loads(ai_response)
        except Exception as e:
            generated = {
                'title': name,
                'subtitle': 'Коммерческое предложение',
                'sections': [{'title': 'Описание услуги', 'description': 'Заполните данные вручную'}],
                'colors': {'primary': '#1d4ed8', 'secondary': '#0f1629', 'accent': '#2563eb'},
                'font': 'Inter',
                'ai_error': str(e)
            }

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        name_esc = name.replace("'", "''")
        tg_esc = telegram_contact.replace("'", "''")
        generated_esc = json.dumps(generated).replace("'", "''")
        cur.execute(
            f"INSERT INTO {schema}.submissions "
            f"(name, email, telegram_contact, old_kp_url, old_kp_filename, reference_kp_url, reference_kp_filename, "
            f"status, generated_content) "
            f"VALUES ('{name_esc}', '', '{tg_esc}', '{old_kp_url}', '{old_kp_filename}', "
            f"'{reference_kp_url}', '{reference_kp_filename}', 'generated', '{generated_esc}'::jsonb) "
            f"RETURNING id, created_at"
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'id': row[0],
                'status': 'generated',
                'created_at': row[1].isoformat(),
                'generated_content': generated
            })
        }

    if method == 'POST' and action == 'upload_image':
        body = json.loads(event.get('body', '{}'))
        image_file = body.get('image_file')

        if not image_file:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не передан image_file'})
            }

        filename = image_file.get('filename', 'image.png')
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        content_type = image_file.get('content_type', 'image/png')
        data = base64.b64decode(image_file['data'])
        key = f'submissions/images/{uuid.uuid4()}_{safe_name}'
        url = upload_bytes(s3, bucket_cdn_id, key, data, content_type)

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'url': url})
        }

    if method == 'PUT' and action == 'update':
        body = json.loads(event.get('body', '{}'))
        submission_id = body.get('id')
        generated_content = body.get('generated_content')

        if not submission_id or not generated_content:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не переданы id или generated_content'})
            }

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        content_esc = json.dumps(generated_content).replace("'", "''")
        id_esc = str(int(submission_id))
        cur.execute(
            f"UPDATE {schema}.submissions SET generated_content = '{content_esc}'::jsonb "
            f"WHERE id = {id_esc} RETURNING id"
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if not row:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Заявка не найдена'})
            }

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'id': row[0], 'status': 'updated'})
        }

    if method == 'POST' and action == 'send':
        body = json.loads(event.get('body', '{}'))
        submission_id = body.get('id')

        if not submission_id:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не передан id заявки'})
            }

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        id_esc = str(int(submission_id))
        cur.execute(
            f"SELECT name, telegram_contact, generated_content FROM {schema}.submissions WHERE id = {id_esc}"
        )
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Заявка не найдена'})
            }

        name, telegram_contact, generated_content = row

        admin_chat_id = os.environ.get('TELEGRAM_ADMIN_CHAT_ID')
        content = generated_content or {}
        summary = (
            f'📄 Новое КП готово для отправки клиенту\n\n'
            f'Клиент: {name}\n'
            f'Telegram/номер клиента: {telegram_contact}\n'
            f'Заголовок КП: {content.get("title", "")}\n\n'
            f'Свяжитесь с клиентом и отправьте готовое предложение.'
        )
        send_telegram_message(admin_chat_id, summary)

        cur.execute(
            f"UPDATE {schema}.submissions SET status = 'sent' WHERE id = {id_esc} RETURNING id"
        )
        conn.commit()
        cur.close()
        conn.close()

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'id': submission_id, 'status': 'sent'})
        }

    if method == 'GET' and action == 'get':
        submission_id = params.get('id')
        if not submission_id:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не передан id'})
            }

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        id_esc = str(int(submission_id))
        cur.execute(
            f"SELECT id, name, telegram_contact, old_kp_url, old_kp_filename, "
            f"reference_kp_url, reference_kp_filename, status, created_at, generated_content "
            f"FROM {schema}.submissions WHERE id = {id_esc}"
        )
        r = cur.fetchone()
        cur.close()
        conn.close()

        if not r:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Заявка не найдена'})
            }

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'id': r[0],
                'name': r[1],
                'telegram_contact': r[2],
                'old_kp_url': r[3],
                'old_kp_filename': r[4],
                'reference_kp_url': r[5],
                'reference_kp_filename': r[6],
                'status': r[7],
                'created_at': r[8].isoformat(),
                'generated_content': r[9]
            })
        }

    if method == 'GET':
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, name, telegram_contact, old_kp_url, old_kp_filename, "
            f"reference_kp_url, reference_kp_filename, status, created_at, generated_content "
            f"FROM {schema}.submissions ORDER BY created_at DESC LIMIT 50"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        result = [
            {
                'id': r[0],
                'name': r[1],
                'telegram_contact': r[2],
                'old_kp_url': r[3],
                'old_kp_filename': r[4],
                'reference_kp_url': r[5],
                'reference_kp_filename': r[6],
                'status': r[7],
                'created_at': r[8].isoformat(),
                'generated_content': r[9]
            }
            for r in rows
        ]

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'submissions': result})
        }

    return {
        'statusCode': 405,
        'headers': headers,
        'body': json.dumps({'error': 'Метод не поддерживается'})
    }