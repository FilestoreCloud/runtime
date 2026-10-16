import http from 'k6/http';
import { check, sleep } from 'k6';

// Multi-tenant high-concurrency WebDAV Stress Test Suite for Storix
export const options = {
  stages: [
    { duration: '30s', target: 20 }, // Ramp up to 20 users
    { duration: '1m', target: 50 },  // Stress at 50 concurrent tenants
    { duration: '20s', target: 0 },  // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1200'], // 95% of requests under 500ms
    http_req_failed: ['rate<0.01'],                 // Less than 1% errors allowed
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://demo.storix.dev';
const AUTH = {
  username: __ENV.NC_USER || 'admin',
  password: __ENV.NC_PASSWORD || 'password123',
};

export default function () {
  const tenantId = `tenant-${__VU}`;
  const webdavUrl = `${BASE_URL}/remote.php/dav/files/${AUTH.username}`;
  const params = {
    auth: 'basic',
    headers: {
      'Authorization': `Basic ${btoa(`${AUTH.username}:${AUTH.password}`)}`,
      'Depth': '1',
    },
  };

  // 1. PROPFIND directory listing
  const propfindRes = http.request('PROPFIND', webdavUrl, null, params);
  check(propfindRes, {
    'PROPFIND status is 207 Multi-Status': (r) => r.status === 207 || r.status === 200,
  });

  // 2. Upload sample file (PUT)
  const filename = `stress_${tenantId}_${Date.now()}.txt`;
  const fileUrl = `${webdavUrl}/${filename}`;
  const fileContent = 'Storix High-Throughput Cloud Storage Payload '.repeat(100);

  const putRes = http.put(fileUrl, fileContent, {
    headers: {
      'Authorization': `Basic ${btoa(`${AUTH.username}:${AUTH.password}`)}`,
      'Content-Type': 'text/plain',
    },
  });
  check(putRes, {
    'PUT created file (201 or 204)': (r) => r.status === 201 || r.status === 204,
  });

  // 3. Download uploaded file (GET)
  const getRes = http.get(fileUrl, {
    headers: {
      'Authorization': `Basic ${btoa(`${AUTH.username}:${AUTH.password}`)}`,
    },
  });
  check(getRes, {
    'GET returned file content (200)': (r) => r.status === 200,
  });

  // 4. Delete file (DELETE)
  const delRes = http.del(fileUrl, null, {
    headers: {
      'Authorization': `Basic ${btoa(`${AUTH.username}:${AUTH.password}`)}`,
    },
  });
  check(delRes, {
    'DELETE cleaned file (204)': (r) => r.status === 204 || r.status === 200,
  });

  sleep(1);
}
