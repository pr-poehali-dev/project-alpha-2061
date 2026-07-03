import json
import os
import base64
import uuid
import re
import psycopg2
import boto3


def handler(event: dict, context) -> dict:
    '''Приём заявок: загрузка старого КП и референса дизайна, сохранение в S3 и БД, получение списка заявок по email'''
    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
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

    if method == 'POST':
        body = json.loads(event.get('body', '{}'))
        name = body.get('name', '').strip()
        email = body.get('email', '').strip()
        phone = body.get('phone', '').strip()
        old_kp = body.get('old_kp_file')
        reference_kp = body.get('reference_kp_file')

        if not name or not email or not old_kp or not reference_kp:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Заполните имя, email и загрузите оба файла'})
            }

        s3 = boto3.client(
            's3',
            endpoint_url='https://bucket.poehali.dev',
            aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY']
        )
        bucket_cdn_id = os.environ['AWS_ACCESS_KEY_ID']

        submission_id = str(uuid.uuid4())

        def upload_file(file_obj, prefix):
            filename = file_obj.get('filename', 'file.pdf')
            safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
            content_type = file_obj.get('content_type', 'application/octet-stream')
            data = base64.b64decode(file_obj['data'])
            key = f'submissions/{submission_id}/{prefix}_{safe_name}'
            s3.put_object(Bucket='files', Key=key, Body=data, ContentType=content_type)
            url = f'https://cdn.poehali.dev/projects/{bucket_cdn_id}/bucket/{key}'
            return url, safe_name

        old_kp_url, old_kp_filename = upload_file(old_kp, 'old')
        reference_kp_url, reference_kp_filename = upload_file(reference_kp, 'ref')

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        name_esc = name.replace("'", "''")
        email_esc = email.replace("'", "''")
        phone_esc = phone.replace("'", "''")
        cur.execute(
            f"INSERT INTO {schema}.submissions "
            f"(name, email, phone, old_kp_url, old_kp_filename, reference_kp_url, reference_kp_filename, status) "
            f"VALUES ('{name_esc}', '{email_esc}', '{phone_esc}', '{old_kp_url}', '{old_kp_filename}', "
            f"'{reference_kp_url}', '{reference_kp_filename}', 'new') RETURNING id, created_at"
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'id': row[0], 'status': 'new', 'created_at': row[1].isoformat()})
        }

    if method == 'GET':
        params = event.get('queryStringParameters') or {}
        email = (params.get('email') or '').strip()

        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        if email:
            email_esc = email.replace("'", "''")
            cur.execute(
                f"SELECT id, name, email, phone, old_kp_url, old_kp_filename, "
                f"reference_kp_url, reference_kp_filename, status, created_at "
                f"FROM {schema}.submissions WHERE email = '{email_esc}' ORDER BY created_at DESC"
            )
        else:
            cur.execute(
                f"SELECT id, name, email, phone, old_kp_url, old_kp_filename, "
                f"reference_kp_url, reference_kp_filename, status, created_at "
                f"FROM {schema}.submissions ORDER BY created_at DESC LIMIT 50"
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        result = [
            {
                'id': r[0],
                'name': r[1],
                'email': r[2],
                'phone': r[3],
                'old_kp_url': r[4],
                'old_kp_filename': r[5],
                'reference_kp_url': r[6],
                'reference_kp_filename': r[7],
                'status': r[8],
                'created_at': r[9].isoformat()
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
