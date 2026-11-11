export interface CustomerProfile {
  id: string;
  name: string;
  phone: string;
  email: string;
  address: string;
}

export interface OrderItem {
  id: string;
  name: string;
  quantity: number;
  price: number;
  image: string;
  returnable: boolean;
}

export interface TrackingEvent {
  status: string;
  location: string;
  timestamp: string;
}

export interface PaymentSummary {
  method: string;
  amount: number;
  subtotal: number;
  shipping: number;
  tax: number;
  already_refunded: boolean;
  refund_id?: string | null;
}

export interface PickupDetails {
  id: string;
  date: string;
  window: string;
  address: string;
  courier_note?: string;
}

export interface Order {
  id: string;
  customer: CustomerProfile;
  items: OrderItem[];
  status: 'Processing' | 'In Transit' | 'Delivered' | 'Cancelled';
  placed_at: string;
  delivered_on?: string | null;
  return_window_end?: string | null;
  returnable: boolean;
  already_refunded: boolean;
  refund_id?: string | null;
  delayed: boolean;
  days_delayed: number;
  eta?: string | null;
  tracking: TrackingEvent[];
  payment: PaymentSummary;
  pickup_scheduled?: PickupDetails | null;
  voucher_issued: boolean;
  voucher_code?: string | null;
  replacement_requested?: boolean;
  replacement_id?: string | null;
  replacement_order_id?: string | null;
}

export interface InteractiveOption {
  id: string;
  label: string;
  sublabel?: string;
  value: string;
}

export interface InteractiveOptionsData {
  kind: 'address' | 'slot' | 'resolution' | 'reason';
  title: string;
  options: InteractiveOption[];
}

export type CallState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'reconnecting' | 'ended';

export interface TranscriptBubble {
  id: string;
  speaker: 'customer' | 'agent' | 'system';
  text: string;
  timestamp: string;
  interrupted?: boolean;
  action_chip?: string;
}

export interface CallSummaryData {
  session_id: string;
  order_id: string;
  resolution: string;
  reference_ids: Record<string, string>;
  actions_taken: Array<{ tool: string; ok: boolean; summary: string; timestamp: string }>;
  summary_text: string;
  rating?: number | null;
  feedback_comment?: string | null;
  duration_seconds: number;
}

