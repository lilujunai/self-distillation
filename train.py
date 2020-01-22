import os
import torch
import torch.nn as nn
import torch.optim as optim
import torch.backends.cudnn as cudnn

import torchvision
import torchvision.transforms as transforms
import new
import pickle
import numpy as np
from model import shake_shake
from cosine_optim import cosine_annealing_scheduler
import argparse
import cross_entropy as loss
import frequency as f

# from tensorboardX import SummaryWriter


parser = argparse.ArgumentParser(description='cifar10 classification models')
parser.add_argument('--lr', default=0.2, help='')
parser.add_argument('--resume', default=None, help='')
parser.add_argument('--batch_size', default=128, help='')
parser.add_argument('--num_worker', default=4, help='')
parser.add_argument('--epochs', default=1800, help='')
parser.add_argument('--logdir', type=str, default='logs', help='')
parser.add_argument('--gpu_id', default='0',
                    help='gpu_id')
parser.add_argument('--dis', default=0,
                    help='self distillation?')
args = parser.parse_args()

if args.dis:
    save_name='dis'
    criterion = loss.InterpolationLoss3()
    print('start train with distillation')
else:
    save_name='no_dis'
    criterion = nn.CrossEntropyLoss()
    print('start train without distillation')


device = 'cuda' if torch.cuda.is_available() else 'cpu'
os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu_id
print('==> Preparing data..')
transforms_train = transforms.Compose([
    transforms.RandomCrop(32, padding=4),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])
transforms_test = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
])
file_name = 'C:/Users/x1c/.keras/datasets'
dataset_train = new.CIFAR10(root=file_name, train=True, download=False, transform=transforms_train)
dataset_test = new.CIFAR10(root=file_name, train=False, download=False, transform=transforms_test)
train_loader = torch.utils.data.DataLoader(dataset_train, batch_size=args.batch_size,
                                           shuffle=True, num_workers=args.num_worker)
test_loader = torch.utils.data.DataLoader(dataset_test, batch_size=100,
                                          shuffle=False, num_workers=args.num_worker)
fre_loader = torch.utils.data.DataLoader(dataset_test, batch_size=100,
                                          shuffle=False, num_workers=args.num_worker)

# there are 10 classes so the dataset name is cifar-10
classes = ('plane', 'car', 'bird', 'cat', 'deer',
           'dog', 'frog', 'horse', 'ship', 'truck')

print('==> Making model..')

net = shake_shake()
net = net.to(device)

if args.resume is not None:
    checkpoint = torch.load('./save_model/' + args.resume)
    net.load_state_dict(checkpoint['net'])


optimizer = optim.SGD(net.parameters(), lr=args.lr,
                      momentum=0.9, weight_decay=1e-4)

cosine_lr_scheduler = cosine_annealing_scheduler(optimizer, args.epochs, args.lr)


# writer = SummaryWriter(args.logdir)


def train(epoch):
    net.train()
    train_loss = 0
    correct = 0
    total = 0

    for batch_idx, (inputs, targets) in enumerate(train_loader):
        inputs = inputs.to(device)
        targets = targets.to(device)
        outputs = net(inputs)
        loss = criterion(outputs, targets)

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        train_loss += loss.item()
        _, predicted = outputs.max(1)
        total += targets.size(0)
        correct += predicted.eq(targets).sum().item()

    acc = 100 * correct / total
    print('epoch : {} [{}/{}]| loss: {:.3f} | acc: {:.3f}'.format(
        epoch, batch_idx, len(train_loader), train_loss / (batch_idx + 1), acc))
    data_write={'epoch':epoch,'train_loss':train_loss / (batch_idx + 1),'train_acc':acc}
    with open(str(epoch) +save_name+'_train.txt', 'wb') as file_pi:
        pickle.dump(data_write, file_pi)


# writer.add_scalar('log/train error', 100 - acc, epoch)


def test(epoch, best_acc):
    net.eval()

    test_loss = 0
    correct = 0
    total = 0

    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(test_loader):
            inputs = inputs.to(device)
            targets = targets.to(device)
            outputs = net(inputs)
            loss = criterion(outputs, targets)

            test_loss += loss.item()
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()

    acc = 100 * correct / total
    print('test epoch : {} [{}/{}]| loss: {:.3f} | acc: {:.3f}'.format(
        epoch, batch_idx, len(test_loader), test_loss / (batch_idx + 1), acc))

    data_write={'epoch':epoch,'test_loss':test_loss / (batch_idx + 1),'test_acc':acc,'fre':fre(epoch)}
    with open(str(epoch) +save_name+'_test.txt', 'wb') as file_pi:
        pickle.dump(data_write, file_pi)

    # writer.add_scalar('log/test error', 100 - acc, epoch)

    if acc > best_acc:
        print('==> Saving model..')
        state = {
            'net': net.state_dict(),
            'acc': acc,
            'epoch': epoch,
        }
        if not os.path.isdir('save_model'):
            os.mkdir('save_model')
        torch.save(state, './save_model/newckpt'+save_name+'.pth')
        best_acc = acc

    return best_acc


def fre(epoch):
    inputs_all=np.zeros((10000,3,32,32))
    outputs_all=np.zeros((10000,10))
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(fre_loader):
            inputs = inputs.to(device)
            outputs = net(inputs)
            #inputs = float(inputs)
            #outputs = float(inputs)
            inputs = inputs.to('cpu').detach()
            outputs = outputs.to('cpu').detach()
            targets = targets.numpy()
            inputs = inputs.numpy()
            outputs = outputs.numpy()
            inputs_all[batch_idx*100:batch_idx*100+100] = inputs
            outputs_all[batch_idx*100:batch_idx*100+100] = outputs
    result=f.cifar(inputs_all,outputs_all,delta=[1,10,100,200,300,400,500,600,700,800,900,1000])
    print('epoch:{} delta:{}'.format(
            epoch,result))
    return result
            #loss = criterion(outputs, targets)

if __name__ == '__main__':
    best_acc = 0
    if args.resume is None:
        for epoch in range(args.epochs):
            cosine_lr_scheduler.step()
            train(epoch)
            best_acc = test(epoch, best_acc)
            torch.cuda.empty_cache()
            
            print('best test accuracy is ', best_acc)
    else:
        test(epoch=0, best_acc=0)
