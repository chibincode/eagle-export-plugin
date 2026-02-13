# 后端集成指南

本文档说明如何在后端处理 Eagle Data Exporter 导出的数据。

## 📦 三种导出模式

### 模式 1: 仅元数据（推荐用于已有图片 URL 的场景）

**适用场景：** 图片已上传到云存储，只需要同步元数据

**JSON 数据示例：**
```json
[
  {
    "id": "abc123",
    "name": "产品设计.png",
    "url": "https://cdn.example.com/image.png",
    "tags": ["UI", "设计"],
    "size": 524288,
    "ext": "png"
  }
]
```

**后端处理（Node.js 示例）：**
```javascript
// 直接解析 JSON 并保存到数据库
const fs = require('fs');
const data = JSON.parse(fs.readFileSync('eagle_export.json', 'utf8'));

data.forEach(async (item) => {
  await db.images.create({
    name: item.name,
    url: item.url,
    tags: item.tags,
    size: item.size
  });
});
```

---

### 模式 2: Base64 编码（推荐用于少量小图片）

**适用场景：** 
- 图片数量少（< 10 张）
- 图片体积小（< 500KB）
- 需要一次性上传所有数据

**JSON 数据示例：**
```json
[
  {
    "id": "abc123",
    "name": "icon.png",
    "url": "https://example.com/source.png",
    "tags": ["icon"],
    "imageBase64": "data:image/png;base64,iVBORw0KGgo..."
  }
]
```

**后端处理（Node.js + Express 示例）：**
```javascript
const fs = require('fs');
const path = require('path');

// 解析并保存图片
data.forEach(async (item) => {
  if (item.imageBase64) {
    // 提取 Base64 数据
    const matches = item.imageBase64.match(/^data:image\/(\w+);base64,(.+)$/);
    if (matches) {
      const ext = matches[1]; // png, jpg, etc.
      const base64Data = matches[2];
      
      // 转换为 Buffer
      const buffer = Buffer.from(base64Data, 'base64');
      
      // 保存到本地
      const filename = `${item.id}.${ext}`;
      const filepath = path.join(__dirname, 'uploads', filename);
      fs.writeFileSync(filepath, buffer);
      
      // 或上传到云存储
      const uploadedUrl = await uploadToS3(buffer, filename);
      
      // 保存到数据库
      await db.images.create({
        name: item.name,
        url: uploadedUrl || item.url,
        tags: item.tags,
        localPath: filepath
      });
    }
  }
});
```

**Python + Flask 示例：**
```python
import json
import base64
from pathlib import Path

# 读取 JSON
with open('eagle_export.json', 'r') as f:
    data = json.load(f)

for item in data:
    if 'imageBase64' in item:
        # 解析 Base64
        header, encoded = item['imageBase64'].split(',', 1)
        image_data = base64.b64decode(encoded)
        
        # 保存文件
        ext = item['ext']
        filename = f"{item['id']}.{ext}"
        filepath = Path('uploads') / filename
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        # 保存到数据库
        db.images.insert({
            'name': item['name'],
            'url': item['url'],
            'tags': item['tags'],
            'local_path': str(filepath)
        })
```

---

### 模式 3: 完整数据包 ⭐ **强烈推荐**

**适用场景：** 
- 大量图片（> 10 张）
- 图片体积大
- 需要同时上传图片文件和元数据
- 生产环境推荐方案

**数据结构：**
```
eagle_export_2026-01-11.zip
├── metadata.json
└── images/
    ├── abc123.png
    ├── def456.jpg
    └── ghi789.png
```

**metadata.json：**
```json
[
  {
    "id": "abc123",
    "name": "产品设计.png",
    "url": "https://example.com/source.png",
    "tags": ["UI", "设计"],
    "imageFile": "abc123.png"
  }
]
```

**后端处理（Node.js 示例）：**
```javascript
const AdmZip = require('adm-zip');
const fs = require('fs');
const path = require('path');

// 解压 ZIP 文件
const zip = new AdmZip('eagle_export_2026-01-11.zip');
zip.extractAllTo('./temp', true);

// 读取元数据
const metadata = JSON.parse(
  fs.readFileSync('./temp/metadata.json', 'utf8')
);

// 处理每个图片
for (const item of metadata) {
  const imagePath = path.join('./temp/images', item.imageFile);
  
  if (fs.existsSync(imagePath)) {
    // 上传到云存储（S3, OSS, etc.）
    const uploadedUrl = await uploadToCloud(imagePath);
    
    // 保存到数据库
    await db.images.create({
      id: item.id,
      name: item.name,
      url: uploadedUrl,
      originalUrl: item.url,
      tags: item.tags,
      size: item.size
    });
  }
}

// 清理临时文件
fs.rmSync('./temp', { recursive: true });
```

**Python + FastAPI 示例：**
```python
import zipfile
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
import shutil

app = FastAPI()

@app.post("/upload-eagle-export")
async def upload_eagle_export(file: UploadFile = File(...)):
    # 保存上传的 ZIP
    temp_zip = Path('temp.zip')
    with open(temp_zip, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    
    # 解压
    extract_dir = Path('extracted')
    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    
    # 读取元数据
    with open(extract_dir / 'metadata.json', 'r') as f:
        metadata = json.load(f)
    
    results = []
    
    # 处理每个图片
    for item in metadata:
        image_path = extract_dir / 'images' / item['imageFile']
        
        if image_path.exists():
            # 上传到云存储
            uploaded_url = await upload_to_s3(image_path)
            
            # 保存到数据库
            db_item = await db.images.create({
                'id': item['id'],
                'name': item['name'],
                'url': uploaded_url,
                'original_url': item.get('url'),
                'tags': item.get('tags', [])
            })
            
            results.append(db_item)
    
    # 清理临时文件
    temp_zip.unlink()
    shutil.rmtree(extract_dir)
    
    return {
        'success': True,
        'imported': len(results)
    }
```

---

## 🔧 实用工具函数

### 批量上传到 AWS S3

```javascript
const AWS = require('aws-sdk');
const s3 = new AWS.S3();

async function uploadToS3(filePath, filename) {
  const fileContent = fs.readFileSync(filePath);
  
  const params = {
    Bucket: 'your-bucket-name',
    Key: `eagle-imports/${filename}`,
    Body: fileContent,
    ContentType: getMimeType(filename)
  };
  
  const result = await s3.upload(params).promise();
  return result.Location; // 返回 CDN URL
}
```

### 批量上传到阿里云 OSS

```javascript
const OSS = require('ali-oss');

const client = new OSS({
  region: 'oss-cn-hangzhou',
  accessKeyId: 'YOUR_ACCESS_KEY',
  accessKeySecret: 'YOUR_SECRET_KEY',
  bucket: 'your-bucket-name'
});

async function uploadToOSS(filePath, filename) {
  const result = await client.put(
    `eagle-imports/${filename}`,
    filePath
  );
  return result.url;
}
```

---

## 📊 对比表格

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| 仅元数据 | 文件小，传输快 | 需要图片已有 URL | 已上传图片的元数据同步 |
| Base64 | 一次性传输，简单 | 文件大 3-4 倍，不适合大图 | 少量小图标、缩略图 |
| 完整数据包 | 支持大量图片，高效 | 需要解压处理 | 生产环境，批量导入 ⭐ |

---

## 🎯 推荐方案

**小型项目（< 100 张图）：** Base64 模式
**中大型项目（> 100 张图）：** 完整数据包模式
**仅需元数据同步：** 仅元数据模式

---

## 💡 最佳实践

1. **使用事务处理** - 确保图片和元数据同时成功
2. **异步上传** - 大量图片时使用队列系统（Bull, RabbitMQ）
3. **进度反馈** - 提供上传进度 API
4. **错误处理** - 记录失败的图片，支持重试
5. **CDN 加速** - 上传后自动分发到 CDN
6. **数据验证** - 验证图片格式、大小、元数据完整性

---

需要更多集成示例？欢迎提 Issue！
