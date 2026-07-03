import json
import os
import base64
import uuid
import re
import io
import urllib.request
import psycopg2
import boto3
import fitz
from xhtml2pdf import pisa


def upload_bytes(s3, bucket_cdn_id, key, data, content_type):
    s3.put_object(Bucket='files', Key=key, Body=data, ContentType=content_type)
    return f'https://cdn.poehali.dev/projects/{bucket_cdn_id}/bucket/{key}'


def fetch_bytes(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def extract_pdf_text(data, max_chars=5000):
    doc = fitz.open(stream=data, filetype='pdf')
    text = ''
    for page in doc:
        text += page.get_text()
        if len(text) >= max_chars:
            break
    doc.close()
    return text[:max_chars]


def render_pdf_pages_as_images(data, max_pages=2, zoom=1.4):
    doc = fitz.open(stream=data, filetype='pdf')
    images = []
    matrix = fitz.Matrix(zoom, zoom)
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(matrix=matrix)
        images.append(pix.tobytes('png'))
    doc.close()
    return images


def call_mistral_vision(old_kp_text, reference_images, name):
    api_key = os.environ['MISTRAL_API_KEY']

    content = [
        {
            'type': 'text',
            'text': (
                'Вот изображения страниц примера дизайна коммерческого предложения (референс), '
                'который нравится клиенту. Внимательно изучи макет: расположение блоков, цвета, '
                'шрифты, отступы, иконки, стиль заголовков и разделителей.\n\n'
                f'Данные клиента "{name}" для нового КП (взяты из его старого документа):\n'
                f'{old_kp_text}\n\n'
                'Собери ПОЛНЫЙ HTML-документ (с тегом <html>, <head> с <style> внутри, и <body>), '
                'который максимально точно ВИЗУАЛЬНО ПОВТОРЯЕТ дизайн референса (цвета, расположение блоков, '
                'типографику, отступы, стиль секций), но заполнен реальными данными клиента вместо содержимого референса. '
                'Используй только inline CSS и <style> в <head> (без внешних файлов и шрифтов из интернета, '
                'кроме стандартных системных шрифтов). Документ должен быть готов для конвертации в PDF формата A4. '
                'Ответь строго в формате JSON: {"html": "<полный HTML документ одной строкой>"}'
            )
        }
    ]

    for img_bytes in reference_images:
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        content.append({
            'type': 'image_url',
            'image_url': f'data:image/png;base64,{b64}'
        })

    payload = {
        'model': 'pixtral-large-latest',
        'messages': [
            {'role': 'user', 'content': content}
        ],
        'temperature': 0.4,
        'response_format': {'type': 'json_object'}
    }

    req = urllib.request.Request(
        'https://api.mistral.ai/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    return result['choices'][0]['message']['content']


def html_to_pdf_bytes(html):
    output = io.BytesIO()
    pisa.CreatePDF(src=html, dest=output, encoding='utf-8')
    return output.getvalue()


def send_telegram_document(chat_id, document_url, caption):
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token or not chat_id:
        return
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{bot_token}/sendDocument',
        data=json.dumps({'chat_id': chat_id, 'document': document_url, 'caption': caption}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


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
    '''Приём заявок на генерацию КП: ИИ анализирует картинки страниц референса дизайна и старое КП клиента, собирает точную HTML-копию и конвертирует в PDF'''
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

    if method == 'POST' and action == 'chunk_init':
        body = json.loads(event.get('body', '{}'))
        filename = body.get('filename', 'file.pdf')
        prefix = body.get('prefix', 'file')

        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        key = f'submissions/{uuid.uuid4()}/{prefix}_{safe_name}'

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'key': key, 'filename': safe_name})
        }

    if method == 'POST' and action == 'chunk_append':
        body = json.loads(event.get('body', '{}'))
        key = body.get('key')
        chunk_b64 = body.get('data', '')
        content_type = body.get('content_type', 'application/octet-stream')
        is_last = body.get('is_last', False)

        if not key or chunk_b64 is None:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не переданы key или data'})
            }

        chunk_bytes = base64.b64decode(chunk_b64)

        try:
            existing = s3.get_object(Bucket='files', Key=key)['Body'].read()
        except Exception:
            existing = b''

        combined = existing + chunk_bytes
        s3.put_object(Bucket='files', Key=key, Body=combined, ContentType=content_type)

        result = {'status': 'ok'}
        if is_last:
            result['cdn_url'] = f'https://cdn.poehali.dev/projects/{bucket_cdn_id}/bucket/{key}'
            result['key'] = key

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(result)
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

        try:
            old_kp_bytes = fetch_bytes(old_kp_url)
            reference_bytes = fetch_bytes(reference_kp_url)

            old_kp_text = extract_pdf_text(old_kp_bytes)
            reference_images = render_pdf_pages_as_images(reference_bytes)

            ai_response = call_mistral_vision(old_kp_text, reference_images, name)
            generated = json.loads(ai_response)
            html_content = generated.get('html', '')

            pdf_bytes = html_to_pdf_bytes(html_content)
            pdf_key = f'submissions/{uuid.uuid4()}/result.pdf'
            pdf_url = upload_bytes(s3, bucket_cdn_id, pdf_key, pdf_bytes, 'application/pdf')
            ai_error = None
        except Exception as e:
            html_content = (
                f'<html><body style="font-family:sans-serif;padding:40px">'
                f'<h1>{name}</h1><p>Не удалось автоматически собрать дизайн. '
                f'Попробуйте другой файл референса.</p></body></html>'
            )
            pdf_bytes = html_to_pdf_bytes(html_content)
            pdf_key = f'submissions/{uuid.uuid4()}/result.pdf'
            pdf_url = upload_bytes(s3, bucket_cdn_id, pdf_key, pdf_bytes, 'application/pdf')
            ai_error = str(e)

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        name_esc = name.replace("'", "''")
        tg_esc = telegram_contact.replace("'", "''")
        html_esc = html_content.replace("'", "''")
        cur.execute(
            f"INSERT INTO {schema}.submissions "
            f"(name, email, telegram_contact, old_kp_url, old_kp_filename, reference_kp_url, reference_kp_filename, "
            f"status, html_content, pdf_url) "
            f"VALUES ('{name_esc}', '', '{tg_esc}', '{old_kp_url}', '{old_kp_filename}', "
            f"'{reference_kp_url}', '{reference_kp_filename}', 'generated', '{html_esc}', '{pdf_url}') "
            f"RETURNING id, created_at"
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        response_body = {
            'id': row[0],
            'status': 'generated',
            'created_at': row[1].isoformat(),
            'html_content': html_content,
            'pdf_url': pdf_url
        }
        if ai_error:
            response_body['ai_error'] = ai_error

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(response_body)
        }

    if method == 'PUT' and action == 'update':
        body = json.loads(event.get('body', '{}'))
        submission_id = body.get('id')
        html_content = body.get('html_content')

        if not submission_id or html_content is None:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Не переданы id или html_content'})
            }

        pdf_bytes = html_to_pdf_bytes(html_content)
        pdf_key = f'submissions/{uuid.uuid4()}/result.pdf'
        pdf_url = upload_bytes(s3, bucket_cdn_id, pdf_key, pdf_bytes, 'application/pdf')

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        html_esc = html_content.replace("'", "''")
        id_esc = str(int(submission_id))
        cur.execute(
            f"UPDATE {schema}.submissions SET html_content = '{html_esc}', pdf_url = '{pdf_url}' "
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
            'body': json.dumps({'id': row[0], 'status': 'updated', 'pdf_url': pdf_url})
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
            f"SELECT name, telegram_contact, pdf_url FROM {schema}.submissions WHERE id = {id_esc}"
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

        name, telegram_contact, pdf_url = row

        admin_chat_id = os.environ.get('TELEGRAM_ADMIN_CHAT_ID')
        caption = f'📄 Новое КП готово\nКлиент: {name}\nКонтакт: {telegram_contact}'
        if pdf_url:
            send_telegram_document(admin_chat_id, pdf_url, caption)
        else:
            send_telegram_message(admin_chat_id, caption)

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
            f"reference_kp_url, reference_kp_filename, status, created_at, html_content, pdf_url "
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
                'html_content': r[9],
                'pdf_url': r[10]
            })
        }

    if method == 'GET':
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute(
            f"SELECT id, name, telegram_contact, old_kp_url, old_kp_filename, "
            f"reference_kp_url, reference_kp_filename, status, created_at, pdf_url "
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
                'pdf_url': r[9]
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
