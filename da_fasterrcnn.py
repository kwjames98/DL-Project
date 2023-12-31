# -*- coding: utf-8 -*-
"""DA-FasterRCNN.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1AA3AxbbBqYvjz2jjIRejGzJePZsxQMfK
"""

from torch.utils.data import Dataset
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw

class DetectionDataset(Dataset):
    def __init__(self, root, meta_path, transform, split='train', train_val_ratio=0.8):
        super().__init__()
        self.root = root
        self.split = split
        self.transform = transform

        if split in ['train', 'val']:
            self.load_meta(meta_path, train_val_ratio)
        else:
            self.load_test_meta(meta_path)

    def load_test_meta(self, meta_path):
        raw_meta = pd.read_csv(meta_path)
        self.meta = []
        n = raw_meta.shape[0]

        for i in range(n):
            image_id = raw_meta['image_id'][i]
            image_path = raw_meta['file_path'][i]
            self.meta.append({'image_id': image_id, 'image_path': image_path})

    def load_meta(self, meta_path, train_val_ratio):
        raw_meta = pd.read_csv(meta_path)
        self.meta = []
        n = raw_meta.shape[0]

        image = Image.open(self.root + raw_meta['file_path'][0][1:])
        width, height = image.size

        for i in range(n):
            image_id = raw_meta['image_id'][i]
            image_path = raw_meta['file_path'][i]
            category_id = raw_meta['category_id'][i]
            bbox = self.bbox_check((raw_meta['x'][i], raw_meta['y'][i], raw_meta['w'][i], raw_meta['h'][i]), width, height)
            area = bbox[2] * bbox[3]

            if image_id > len(self.meta):
                self.meta.append({
                    'image_id': image_id,
                    'image_path': image_path,
                    'objects': {
                        'category': [category_id],
                        'bbox': [bbox],
                        'area': [area],
                    }
                })
            else:
                self.meta[image_id - 1]['objects']['category'].append(category_id)
                self.meta[image_id - 1]['objects']['bbox'].append(bbox)
                self.meta[image_id - 1]['objects']['area'].append(area)

        n_samples = len(self.meta)
        n_train = int(n_samples * train_val_ratio)

        if self.split == 'train':
            self.meta = self.meta[:n_train]
        elif self.split == 'val':
            self.meta = self.meta[n_train:]

    def __getitem__(self, idx):
        if self.split == 'test':
            return self.get_testitem(idx)

        image = Image.open(self.root + self.meta[idx]['image_path'][1:])
        image = np.array(image.convert("RGB"))[:, :, ::-1]
        out = self.transform(
            image=image,
            bboxes=self.meta[idx]['objects']['bbox'],
            category=self.meta[idx]['objects']['category']
        )

        target = {
            "image_id": self.meta[idx]['image_id'],
            "annotations": self.formatted_anns(self.meta[idx]['image_id'],
                                               out['category'],
                                               self.meta[idx]['objects']['area'],
                                               out['bboxes']
                                              )
        }

        return self.image_processor(
            images=out['image'],
            annotations=target,
            return_tensors='pt'
        )

    def get_testitem(self, idx):
        return self.meta[idx]['image_id'], Image.open(self.root + self.meta[idx]['image_path'][1:])

    def bbox_check(self, bbox, width, height):
        x, y, w, h = bbox
        if x < 0.0:
            w -= x
            x = 0
        if x + w >= width:
            w -= (x + w) - width
        if y < 0.0:
            h -= y
            y = 0
        if y + h > height:
            h -= (y + h) - height
        return x, y, w, h

    def formatted_anns(self, image_id, category, area, bbox):
        annotations = []
        for i in range(len(category)):
            annotations.append({
                'image_id': image_id,
                'category_id': category[i],
                'isCrowd': 0,
                'area': area[i],
                'bbox': bbox[i],
            })
        return annotations

    def visualize(self, idx):
        img_path = self.meta[idx]['image_path']
        img = Image.open(self.root + img_path[1:])
        draw = ImageDraw.Draw(img)

        for x, y, w, h in self.meta[idx]['objects']['bbox']:
            draw.rectangle((x, y, x + w, y + h), outline='red', width=1)

        return img

    def __len__(self):
        return len(self.meta)

import albumentations
import numpy as np
import torch


transform = albumentations.Compose(
    [
        albumentations.Resize(480, 480),
        albumentations.HorizontalFlip(p=1.0),
        albumentations.RandomBrightnessContrast(p=1.0),
    ],
    bbox_params=albumentations.BboxParams(format="coco", label_fields=["category"]),
)

train_ds = DetectionDataset(
    '/content/drive/MyDrive/DL_Project/Dataset/SODA10M/train/',
    '/content/drive/MyDrive/DL_Project/Dataset/SODA10M/train/train_source.csv',
    transform,
)

val_ds = DetectionDataset(
    '/content/drive/MyDrive/DL_Project/Dataset/SODA10M/train/',
    '/content/drive/MyDrive/DL_Project/Dataset/SODA10M/train/train_source.csv',
    transform,
    split='val',
)

print('Load Dataset')

df = pd.read_csv('/content/drive/MyDrive/DL_Project/Dataset/SODA10M/category.csv')
n = df.shape[0]

id2label = {}
label2id = {}

for i in range(n):
    Id = int(df['category_id'][i])
    Name = df['name'][i]
    id2label[Id] = Name
    label2id[Name] = Id

print(id2label)
print(label2id)

!git clone https://github.com/yangxu351/DA-Faster-RCNN-PyTorch.git
!cd DA-Faster-RCNN-PyTorch

!pip install -r requirements.txt

from demo.Mask_R_CNN_demo import DAFasterRCNN


model = DAFasterRCNN(pretrained=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

from torch.utils.data import DataLoader

BATCH = 8

def collate_fn(samples):
    images=[s['input'].transpose(0, 2).to(device) for s in samples]
    targets = []

    for s in samples:
        boxes = torch.tensor([obj['bbox'] for obj in s['label']['annotations']])
        boxes[:, 2:] = boxes[:, :2] + boxes[:, 2:] # (x, y, w, h) -> (x1, y1, x2, y2)
        categories = torch.tensor([obj['category_id'] for obj in s['label']['annotations']])
        targets.append({'boxes':boxes.to(device), 'labels':categories.to(device)})

    return {'inputs': images, 'labels': targets}

train_loader = DataLoader(trainset, batch_size=BATCH, shuffle=True, collate_fn=collate_fn)
val_loader = DataLoader(valset, batch_size=BATCH, shuffle=True, collate_fn=collate_fn)

import torchvision
from torchvision.models.detection import FasterRCNN_ResNet50_FPN_Weights
from torch.optim import Adam
from tqdm import tqdm

device = 'cuda' if torch.cuda.is_available() else 'cpu'
num_epoch = 10

model = torchvision.models.detection.fasterrcnn_resnet50_fpn(weights=FasterRCNN_ResNet50_FPN_Weights.DEFAULT).to(device)
optim = Adam(model.parameters(), lr=0.001, momentum=0.9, weight_decay=0.00005)

for epoch in range(1, num_epoch+1):
    model.train()
    epoch_loss = 0

    for batch, data in enumerate(tqdm(train_loader)):
        optim.zero_grad()

        output = model(data['inputs'], data['labels'])

        loss = output['loss_objectness'] + output['loss_rpn_box_reg'] + output['loss_classifier'] +output['loss_box_reg']
        loss.backward()

        optim.step()

        epoch_loss += loss

    print(f"epoch {epoch} loss: {epoch_loss / len(train_loader)}")

model.eval()
with torch.no_grad():
    for image_id, image in tqdm(testset):
        image = np.array(image.convert('RGB'))[:, :, ::-1].copy()
        data = torch.from_numpy(image).float()
        data = data.transpose(0, 2)

        prediction = model([data.to(device)])
        num_object = len(prediction[0]['scores'])

        output = ''
        for i in range(num_object):
            score = prediction[0]['scores'][i]
            label = prediction[0]['labels'][i]
            xmin, ymin, xmax, ymax = prediction[0]['boxes'][i]

            if i == num_object - 1:
                output += f'{label} {score} {xmin} {ymin} {xmax - xmin} {ymax - ymin}'
            else:
                output += f'{label} {score} {xmin} {ymin} {xmax - xmin} {ymax - ymin} '

            if output == '':
                output = 'Null'