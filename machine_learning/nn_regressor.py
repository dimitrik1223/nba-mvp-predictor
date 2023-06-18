import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import copy
import tqdm
import pickle

from scipy.stats import zscore
from sklearn.model_selection import train_test_split
from torch.autograd import Variable
from sklearn import preprocessing
from torch.utils.data import DataLoader, TensorDataset

class EarlyStopping():
  def __init__(self, patience=5, min_delta=1e-2, restore_best_weights=True):
    self.patience = patience
    self.min_delta = min_delta
    self.restore_best_weights = restore_best_weights
    self.best_model = None
    self.best_loss = None
    self.counter = 0
    self.status = ""
    
  def __call__(self, model, val_loss):
    if self.best_loss == None:
      self.best_loss = val_loss
      self.best_model = copy.deepcopy(model)
    elif self.best_loss - val_loss > self.min_delta:
      self.best_loss = val_loss
      self.counter = 0
      self.best_model.load_state_dict(model.state_dict())
    elif self.best_loss - val_loss < self.min_delta:
      self.counter += 1
      if self.counter >= self.patience:
        self.status = f"Stopped on {self.counter}"
        if self.restore_best_weights:
          model.load_state_dict(self.best_model.state_dict())
        return True
    self.status = f"{self.counter}/{self.patience}"
    return False

class Net(nn.Module):
  def __init__(self, in_count, out_count):
    super(Net, self).__init__()
    self.fc1 = nn.Linear(in_count, 50)
    self.fc2 = nn.Linear(50, 25)
    self.fc3 = nn.Linear(25, out_count)
	

  def forward(self, x):
    x = F.relu(self.fc1(x))
    x = F.relu(self.fc2(x))
    return self.fc3(x)


def train_nn(df):
	predictors = df[[
    col for col in df.columns if df[col].dtype in ("float64", "int64") 
	and col not in ("Pts Won", "Pts Max", "Share")
	]]
	device = (
		"cuda"
		if torch.cuda.is_available()
		else "mps"
		if torch.backends.mps.is_available()
		else "cpu"
	)
	print(f"Using {device} device")
	x = predictors.values
	y = df["Pts Won"].values
	
	x_train, x_test, y_train, y_test = train_test_split(
    x, y, test_size=0.25, random_state=0
	)

	# Numpy to Torch Tensor
	x_train = torch.Tensor(x_train).float()
	y_train = torch.Tensor(y_train).float()

	x_test = torch.Tensor(x_test).float().to(device)
	y_test = torch.Tensor(y_test).float().to(device)

	BATCH_SIZE = 16

	dataset_train = TensorDataset(x_train, y_train)
	dataloader_train = DataLoader(dataset_train, \
	batch_size=BATCH_SIZE, shuffle=True)

	dataset_test = TensorDataset(x_train, y_train)
	dataloader_test = DataLoader(dataset_test, \
	batch_size=BATCH_SIZE, shuffle=True)

	# Initialize model
	model = Net(x.shape[1], 1)

	# Define the loss function for regression
	loss_fn = nn.MSELoss()

	# Define the optimizer
	optimizer = torch.optim.Adam(model.parameters())

	es = EarlyStopping()

	epoch = 0
	done = False
	while epoch < 1000 and not done:
		epoch += 1
		steps = list(enumerate(dataloader_train))
		pbar = tqdm.tqdm(steps)
		model.train()
		for i, (x_batch, y_batch) in pbar:
			y_batch_pred = model(x_batch.to(device)).flatten()
			loss = loss_fn(y_batch_pred, y_batch.to(device))
			optimizer.zero_grad()
			loss.backward()
			optimizer.step()

			loss, current = loss.item(), (i + 1) * len(x_batch)
			if i == len(steps) - 1:
				model.eval()
				pred = model(x_test).flatten()
				vloss = loss_fn(pred, y_test)
				if es(model,vloss): done = True
				pbar.set_description(f"Epoch: {epoch}, tloss: {loss}, vloss: {vloss:>7f}, EStop:[{es.status}]")
			else:
				pbar.set_description(f"Epoch: {epoch}, tloss {loss:}")

	pickle.dump(model, open('flask_app/mvp_model.pkl', 'wb'))
