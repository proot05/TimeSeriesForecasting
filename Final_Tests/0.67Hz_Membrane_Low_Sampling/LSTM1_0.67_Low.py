from data.preprocess import TimeSeriesPreprocessor, MembraneDataLoader
from testfuncs.predict import predict
import matplotlib.pyplot as plt
import torch
from models.lstm1 import MyLSTM
from tqdm import tqdm
import os
import numpy as np
from scipy.interpolate import interp1d
from data.evaluate import percent_variance_explained, smape, high_freq_snr
import pylab


device = torch.device('cuda')

multp = 1
params = {'legend.fontsize': 25*multp, 'axes.labelsize': 25*multp, 'axes.titlesize': 25*multp, 'xtick.labelsize': 25*multp,
          'ytick.labelsize': 25*multp}
pylab.rcParams.update(params)

current_dir = os.path.dirname(__file__)

output_dir = current_dir
repo_dir = os.path.abspath(os.path.join(os.path.abspath(os.path.join(current_dir, os.pardir)),os.pardir))
input_dir = os.path.join(repo_dir,'train\\train_output\LSTM1')

state = TimeSeriesPreprocessor.load_state(os.path.join(input_dir, 'checkpoints', 'LSTM1_normalizer.pkl'))
new_dt = state['dt_new']
x_normalizer = state['normalizer']
seq_len = state['seq_len']
train_size = state['train_size']

print("dt = ", new_dt)

checkpoint = torch.load(input_dir + '\checkpoints' + '\checkpoint_50.pt', map_location=device)

model = MyLSTM(InFeatures=1,
                OutFeatures=1,
                num_layers=1,
                HiddenDim=256,
                FeedForwardDim=512,
                nonlinearity = 'tanh')

model.load_state_dict(checkpoint['model_state_dict'])
model.to(device)

# printing out the model size
total_params = sum(p.numel() for p in model.parameters())
print(f"Number of parameters: {total_params}")

model.eval()

# ~9 Hz sampled data (from the training data sample)
freq = 0.67
loader = MembraneDataLoader(date="4-17-25", frequency=freq, number=1, repo_dir=repo_dir)
mem_time, mem_data = loader.load_data()
buffer = 2000
mem_time_test = mem_time[-(seq_len+buffer):]
mem_data_test = mem_data[-(seq_len+buffer):]

# time into the future to predict at
rnn_delay = 0.25  #new_dt

pred_id = [None] * seq_len
pred_id_time = [None] * seq_len

for i in tqdm(range(int((len(mem_time_test) - seq_len)))):

    pred = predict(model, mem_time_test[i:i + seq_len], mem_data_test[i:i + seq_len], new_dt, rnn_delay,
                           seq_len, device, x_normalizer)
    pred_id.append(pred)

    pred_id_time.append(mem_time_test[i + seq_len - 1] + rnn_delay)

mem_time_eval = mem_time_test[seq_len:]
mem_data_eval = mem_data_test[seq_len:]

pred_time_eval = pred_id_time[seq_len:]
pred_data_eval = pred_id[seq_len:]

# Define a common time base
common_time = np.linspace(pred_time_eval[15], mem_time_eval[-1], num=max(len(mem_time_eval), len(pred_time_eval)))

# Interpolate both time series
interp_mem_data = interp1d(mem_time_eval, mem_data_eval, kind='linear', fill_value="extrapolate")
interp_preds_data = interp1d(pred_time_eval, pred_data_eval, kind='linear', fill_value="extrapolate")

mem_data_interp = interp_mem_data(common_time)
preds_data_interp = interp_preds_data(common_time)

#  Compute error as a function of time
error = mem_data_interp - preds_data_interp
# error = mem_data_interp - pred_data_eval

print(f"Future Prediction Time = {rnn_delay:.4f}")

# Print average error (mean absolute error)
average_error = np.mean(np.abs(error))
print(f"MAE = {average_error:.4f}")

pct_var1 = percent_variance_explained(torch.tensor(preds_data_interp, dtype=torch.float32), torch.tensor(mem_data_interp, dtype=torch.float32))
print(f"R² % = {pct_var1:.2f}%")

pct_var2 = smape(torch.tensor(preds_data_interp, dtype=torch.float32), torch.tensor(mem_data_interp, dtype=torch.float32))
print(f"SMAPE = {pct_var2:.2f}%")

fs = 1.0 / (common_time[1] - common_time[0])  # sampling rate in Hz
cutoff = freq
snr_hf = high_freq_snr(torch.tensor(preds_data_interp, dtype=torch.float32), torch.tensor(mem_data_interp, dtype=torch.float32), fs, cutoff)
print(f"High‑pass SNR (> {cutoff} Hz) = {snr_hf:.1f} dB")

# Plotting
fig, ax = plt.subplots(figsize=(20, 16))
lw = 3

ax.plot(mem_time_test, mem_data_test, color='C0', linestyle='solid', linewidth=lw, alpha=1, label='Ground Truth')
ax.plot(pred_id_time, pred_id, color='C1', linestyle='dashdot', linewidth=lw, alpha=1, label='Prediction')
ax.plot(common_time, error, color='C2', linestyle='solid', linewidth=lw, alpha=1, label='Error')
leg = ax.legend(loc='lower left', frameon=True)
leg.get_frame().set_edgecolor('black')
ax.set_xlabel('Time (s)')
ax.set_ylabel('Index')
plt.title(f'MAE = {average_error:.2f}, R² % = {pct_var1:.2f}%, SMAPE = {pct_var2:.2f}%, High‑pass SNR (> {cutoff} Hz) = {snr_hf:.1f} dB')
plt.savefig(output_dir + '\prediction.png', bbox_inches='tight')

plt.xlim([pred_id_time[-1]-5, pred_id_time[-1]])
plt.savefig(output_dir + '\prediction_zoom.png', bbox_inches='tight')

plt.close()
