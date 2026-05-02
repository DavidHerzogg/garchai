import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, TextInput, ActivityIndicator, Dimensions, Platform } from 'react-native';
import { useUser } from '@clerk/expo';
import { useQuery, useMutation } from 'convex/react';
import { api } from '@/convex/_generated/api';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import Svg, { Path } from 'react-native-svg';
import Animated, { FadeInDown, FadeOut } from 'react-native-reanimated';

const { width } = Dimensions.get('window');

const DEFAULT_ENGINE_URL =
  Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
const ENGINE_URL = (process.env.EXPO_PUBLIC_ENGINE_URL || DEFAULT_ENGINE_URL).replace(/\/+$/, '');

type GenerateResponse = {
  code?: unknown;
};

type BacktestResponse = {
  equity?: unknown;
};

async function postEngine<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${ENGINE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  const text = await response.text();
  let payload: any = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error(`Engine returned invalid JSON from ${path}`);
    }
  }

  if (!response.ok) {
    const detail = payload?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : payload?.message || response.statusText || 'Engine request failed';
    throw new Error(message);
  }

  return payload as T;
}

function toNumberArray(value: unknown, label: string): number[] {
  if (!Array.isArray(value)) {
    throw new Error(`Engine response is missing ${label}`);
  }

  const numbers = value.map((item) => Number(item));
  if (numbers.some((item) => !Number.isFinite(item))) {
    throw new Error(`Engine returned invalid ${label} values`);
  }

  return numbers;
}

function downsampleSeries(series: number[], maxPoints = 500): number[] {
  if (series.length <= maxPoints) return series;

  const lastIndex = series.length - 1;
  return Array.from({ length: maxPoints }, (_, index) => {
    const sourceIndex = Math.round((index / (maxPoints - 1)) * lastIndex);
    return series[sourceIndex];
  });
}

// ── Components ──────────────────────────────────────────────────────────────

const MiniChart = ({ data }: { data: number[] }) => {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const h = 40;
  const w = 100;
  
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
  }).join(' ');

  return (
    <Svg width={w} height={h}>
      <Path d={points} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
};

// ── Main Screen ─────────────────────────────────────────────────────────────

export default function StrategyScreen() {
  const { user } = useUser();
  const convexUser = useQuery(api.users.getByClerkId, { clerkId: user?.id ?? '' });
  const strategies = useQuery(api.strategies.list, convexUser?._id ? { userId: convexUser._id } : "skip");
  const createStrategy = useMutation(api.strategies.create);

  const [modalVisible, setModalVisible] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [status, setStatus] = useState<'idle' | 'generating' | 'backtesting' | 'done' | 'error'>('idle');
  const [error, setError] = useState('');

  const handleCreate = async () => {
    if (!prompt.trim() || !convexUser) return;
    const trimmedPrompt = prompt.trim();
    
    setStatus('generating');
    setError('');

    try {
      const generated = await postEngine<GenerateResponse>('/generate', {
        prompt: trimmedPrompt,
      });
      if (typeof generated.code !== 'string' || !generated.code.trim()) {
        throw new Error('Engine did not return generated code');
      }

      setStatus('backtesting');
      const result = await postEngine<BacktestResponse>('/backtest', {
        code: generated.code,
      });
      const equity = toNumberArray(result.equity, 'equity');

      // 2. Save to Convex
      await createStrategy({
        userId: convexUser._id,
        prompt: trimmedPrompt,
        equity: downsampleSeries(equity),
      });

      setStatus('done');
      
      // Smooth close
      setTimeout(() => {
        setModalVisible(false);
        setPrompt('');
        setStatus('idle');
      }, 1500);

    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerSubtitle}>GARCH AI</Text>
          <Text style={styles.headerTitle}>Strategies</Text>
        </View>
        <TouchableOpacity onPress={() => setModalVisible(true)} style={styles.iconBtn}>
          <Ionicons name="add" size={26} color="#FFF" />
        </TouchableOpacity>
      </View>

      <TouchableOpacity 
        style={styles.mainCreateBtn} 
        onPress={() => setModalVisible(true)}
        activeOpacity={0.8}
      >
        <LinearGradient colors={['#22d3ee', '#818cf8']} start={{x:0, y:0}} end={{x:1, y:0}} style={styles.grad}>
          <Ionicons name="flash" size={20} color="#FFF" style={{ marginRight: 8 }} />
          <Text style={styles.btnText}>Create New Strategy</Text>
        </LinearGradient>
      </TouchableOpacity>

      {/* List */}
      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        {strategies === undefined ? (
          <View style={styles.center}>
            <ActivityIndicator color="#22d3ee" />
          </View>
        ) : strategies.length === 0 ? (
          <Animated.View entering={FadeInDown} style={styles.emptyContainer}>
            <Ionicons name="file-tray-outline" size={48} color="#1e2a3b" />
            <Text style={styles.emptyText}>No strategies yet</Text>
            <Text style={styles.emptySub}>Describe a logic to see it here</Text>
          </Animated.View>
        ) : (
          strategies.map((s, idx) => (
            <Animated.View key={s._id} entering={FadeInDown.delay(idx * 50)}>
              <View style={styles.card}>
                <View style={{ flex: 1, marginRight: 12 }}>
                  <Text style={styles.cardPrompt} numberOfLines={2}>{s.prompt}</Text>
                  <View style={styles.cardMeta}>
                    <Ionicons name="calendar-outline" size={12} color="#64748b" />
                    <Text style={styles.cardDate}>{new Date(s.createdAt).toLocaleDateString()}</Text>
                  </View>
                </View>
                <MiniChart data={s.equity} />
              </View>
            </Animated.View>
          ))
        )}
      </ScrollView>

      {/* Create Modal */}
      <Modal visible={modalVisible} animationType="fade" transparent>
        <View style={styles.modalOverlay}>
          <Animated.View entering={FadeInDown} exiting={FadeOut} style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>New Strategy</Text>
              <TouchableOpacity 
                onPress={() => !['generating', 'backtesting'].includes(status) && setModalVisible(false)}
                style={styles.closeBtn}
              >
                <Ionicons name="close" size={24} color="#64748b" />
              </TouchableOpacity>
            </View>

            <Text style={styles.inputLabel}>WHAT IS YOUR TRADING IDEA?</Text>
            <TextInput
              style={[styles.input, status === 'error' && { borderColor: '#f87171' }]}
              placeholder="e.g. Buy when RSI is below 30 and price is above 200 EMA..."
              placeholderTextColor="#475569"
              multiline
              value={prompt}
              onChangeText={setPrompt}
              editable={status === 'idle' || status === 'error'}
            />

            {status !== 'idle' && (
              <View style={styles.statusBox}>
                {status !== 'done' && status !== 'error' && <ActivityIndicator color="#22d3ee" style={{ marginBottom: 12 }} />}
                <Text style={[styles.statusText, status === 'error' && { color: '#f87171' }, status === 'done' && { color: '#4ade80' }]}>
                  {status === 'generating' && '🤖 AI is generating Python code...'}
                  {status === 'backtesting' && '📈 Running backtest on XAUUSD...'}
                  {status === 'done' && '✨ Strategy saved successfully!'}
                  {status === 'error' && `⚠️ Error: ${error}`}
                </Text>
              </View>
            )}

            <View style={{ marginTop: 'auto', paddingTop: 20 }}>
              <TouchableOpacity 
                disabled={status === 'generating' || status === 'backtesting' || !prompt.trim()} 
                onPress={handleCreate}
                style={[styles.submitBtn, (status === 'generating' || status === 'backtesting' || !prompt.trim()) && { opacity: 0.5 }]}
              >
                <Text style={styles.submitBtnText}>
                  {status === 'idle' ? 'Start Generation' : status === 'error' ? 'Try Again' : 'Processing...'}
                </Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0d0f14', paddingHorizontal: 20, paddingTop: 60 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 },
  headerSubtitle: { fontSize: 12, fontWeight: '600', color: '#22d3ee', textTransform: 'uppercase', letterSpacing: 1 },
  headerTitle: { fontSize: 32, fontWeight: '800', color: '#FFF', marginTop: 2 },
  iconBtn: { width: 44, height: 44, borderRadius: 12, backgroundColor: '#161b22', justifyContent: 'center', alignItems: 'center', borderWidth: 1, borderColor: '#1e2a3b' },
  mainCreateBtn: { marginBottom: 24, shadowColor: '#22d3ee', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.2, shadowRadius: 8 },
  grad: { padding: 18, borderRadius: 16, alignItems: 'center', flexDirection: 'row', justifyContent: 'center' },
  btnText: { color: '#FFF', fontWeight: '800', fontSize: 16, letterSpacing: 0.5 },
  list: { paddingBottom: 120 },
  card: { backgroundColor: '#161b22', padding: 18, borderRadius: 16, marginBottom: 14, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: '#1e2a3b' },
  cardPrompt: { color: '#f8fafc', fontSize: 15, fontWeight: '600', marginBottom: 8, lineHeight: 20 },
  cardMeta: { flexDirection: 'row', alignItems: 'center' },
  cardDate: { color: '#64748b', fontSize: 12, marginLeft: 4, fontWeight: '500' },
  emptyContainer: { alignItems: 'center', marginTop: 80 },
  emptyText: { color: '#e2e8f0', fontSize: 18, fontWeight: '700', marginTop: 16 },
  emptySub: { color: '#64748b', fontSize: 14, marginTop: 4 },
  center: { marginTop: 40 },
  
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: '#0d1117', borderTopLeftRadius: 32, borderTopRightRadius: 32, padding: 24, minHeight: 480, borderWidth: 1, borderColor: '#1e2a3b' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  modalTitle: { color: '#FFF', fontSize: 22, fontWeight: '800' },
  closeBtn: { padding: 4 },
  inputLabel: { color: '#64748b', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 10 },
  input: { backgroundColor: '#0d0f14', borderRadius: 16, padding: 18, color: '#FFF', fontSize: 16, minHeight: 120, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1e2a3b' },
  statusBox: { marginTop: 24, alignItems: 'center', padding: 16, backgroundColor: '#161b22', borderRadius: 16, borderWidth: 1, borderColor: '#1e2a3b' },
  statusText: { color: '#22d3ee', fontWeight: '700', fontSize: 14, textAlign: 'center', lineHeight: 22 },
  submitBtn: { backgroundColor: '#FFF', padding: 18, borderRadius: 16, alignItems: 'center' },
  submitBtnText: { color: '#0d0f14', fontWeight: '800', fontSize: 16 },
});
