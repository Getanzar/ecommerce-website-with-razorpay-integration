import React, { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, AppState, Linking, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { Job, Kind, Listing, Page, partnerRequest, Payout, Role, Roles, SellerOrder, Workspace } from "./partnerApi";
import PartnerForm from "./PartnerForm";
import ProductColors from "./ProductColors";
import { RiderEvidence } from "./PartnerExceptions";
import { SellerOrderRow, SellerOrderDetail } from "./SellerOrders";
import { startTracking, stopTracking, trackedJob } from "./backgroundTracking";
import { NotificationTarget } from "./NotificationInbox";

const money = (amount: string) => `₹${Number(amount || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const label = (text: string) => text.replace(/_/g, " ");
const fail = (error: unknown) => Alert.alert("Unable to continue", error instanceof Error ? error.message : "Please try again.");

function Button({ title, onPress, disabled = false, secondary = false }: { title: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, secondary && s.secondary, disabled && s.disabled]}><Text style={[s.buttonText, secondary && s.secondaryText]}>{title}</Text></Pressable>;
}
function Input({ title, value, onChange, numeric = false }: { title: string; value: string; onChange: (value: string) => void; numeric?: boolean }) {
  return <View style={s.field}><Text style={s.muted}>{title}</Text><TextInput accessibilityLabel={title} style={s.input} value={value} onChangeText={onChange} keyboardType={numeric ? "number-pad" : "default"} autoCapitalize="none" /></View>;
}

function PayoutCard({ row }: { row: Payout }) {
  return <View style={s.card}><Text style={s.cardTitle}>{row.order_id ? `Order #${row.order_id}` : `Delivery #${row.delivery_id}`}</Text><Text style={s.amount}>{money(row.amount)}</Text><Text style={s.badge}>{label(row.status)}</Text>{row.gross && <Text style={s.muted}>Gross {money(row.gross)} · Platform fee {money(row.fee || "0")}</Text>}{row.scheduled_for && <Text style={s.muted}>Scheduled: {new Date(row.scheduled_for).toLocaleString()}</Text>}{!!row.failure_reason && <Text style={s.error}>{row.failure_reason}</Text>}</View>;
}

function ListingCard({
  row,
  kind,
  token,
  refresh,
  edit,
  variant,
  manageColors,
}: {
  row: Listing;
  kind: Kind;
  token: string;
  refresh: () => void;
  edit: () => void;
  variant: (id?: number) => void;
  manageColors: () => void;
}) {

  const [busy, setBusy] = useState(false);
  const [stocks, setStocks] = useState<Record<number, string>>({});
  const save = async (data: unknown) => {
    if (busy) return;
    setBusy(true);
    try { await partnerRequest(token, `seller/${kind}/catalog/${row.id}/`, "PATCH", data); refresh(); setStocks({}); } catch (error) { fail(error); } finally { setBusy(false); }
  };
  return <View style={s.card}><Text style={s.cardTitle}>{row.name}</Text><View style={s.row}><Text style={s.badge}>{row.moderation ? `${row.moderation} · ` : ""}{row.active ? "Live" : "Hidden"}</Text><Switch accessibilityLabel={`Availability of ${row.name}`} value={row.active} disabled={busy || (!row.active && !!row.moderation && row.moderation !== "approved")} onValueChange={(active) => save({ active })} /></View>{!!row.rejection_reason && <Text style={s.error}>{row.rejection_reason}</Text>}
<Button
  secondary
  title="Edit listing"
  onPress={edit}
/>

{kind === "shop" && (
  <Button
    secondary
    title="Manage colors"
    onPress={manageColors}
  />
)}

{kind !== "grocery" && (
  <Button
    secondary
    title="Add variant"
    onPress={() => variant()}
  />
)}
   {row.variants.map(v => <View key={v.id} style={s.variant}><Text style={s.body}>{v.name} · {money(v.price)}</Text>{kind !== "grocery" && <Button secondary title="Edit variant" onPress={() => variant(v.id)} />}{v.stock !== null && <><Input title="Stock quantity" numeric value={stocks[v.id] ?? String(v.stock)} onChange={value => setStocks(prev => ({ ...prev, [v.id]: value }))} /><Button secondary title="Save stock" disabled={busy || !/^\d+$/.test(stocks[v.id] ?? "")} onPress={() => save({ variant_id: v.id, stock: Number(stocks[v.id]) })} /></>}</View>)}</View>;
}

function JobCard({ row, token, refresh, active }: { row: Job; token: string; refresh: () => void; active: boolean }) {
  const [busy, setBusy] = useState(false);
  const [otp, setOtp] = useState("");
  const [cash, setCash] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [locationStatus, setLocationStatus] = useState("");
  const eligible = active && ["accepted", "picked_up", "out_for_delivery"].includes(row.status);
  useEffect(() => {
    trackedJob().then(job => { setSharing(job === row.id); if (job === row.id && !eligible) void stopTracking(); }).catch(fail);
  }, [row.id, eligible]);
  const toggleSharing = async (enabled: boolean) => {
    try { if (enabled) await startTracking(token, row.id); else await stopTracking(); setSharing(enabled); setLocationStatus(enabled ? "Background sharing active. Stop sharing here." : "Location sharing stopped."); } catch (error) { fail(error); }
  };
  const act = async (action: string, data?: unknown, method = "POST") => {
    if (busy) return;
    setBusy(true);
    try { await partnerRequest(token, `rider/jobs/${row.id}/${action}/`, method, data); if (action === "complete") { await stopTracking(); setSharing(false); } setOtp(""); setCash(false); refresh(); } catch (error) { fail(error); } finally { setBusy(false); }
  };
  const navigate = async (address: string) => { try { await Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(address)}`); } catch (error) { fail(error); } };
  return <View style={s.card}><View style={s.row}><Text style={s.cardTitle}>{row.kind} #{row.id}</Text><Text style={s.badge}>{label(row.status)}</Text></View><Text style={s.body}>{row.pickup_name}</Text><Text style={s.muted}>Pickup: {row.pickup_address}</Text><Text style={s.muted}>Delivery area: {row.pincode}</Text>{!!row.delivery_address && <><Text style={s.body}>{row.customer_name}</Text><Text style={s.muted}>Deliver to: {row.delivery_address}</Text></>}<Text style={s.amount}>{money(row.net)} <Text style={s.muted}>your earning</Text></Text><Text style={s.muted}>Gross {money(row.gross)} · Fee {money(row.fee)}</Text>{row.payment_method === "cod" && <Text style={s.cash}>Collect {money(row.collection_amount)} cash</Text>}{row.status === "available" && <Button title={busy ? "Accepting…" : "Accept delivery"} disabled={busy} onPress={() => act("accept")} />}{active && <><View style={s.wrap}><Button secondary title="Navigate to pickup" onPress={() => navigate(row.pickup_address)} />{!!row.delivery_address && <Button secondary title="Navigate to customer" onPress={() => navigate(row.delivery_address)} />}{!!row.customer_phone && <Button secondary title="Call customer" onPress={() => { Linking.openURL(`tel:${row.customer_phone.replace(/[^+\d]/g, "")}`).catch(fail); }} />}</View>{row.next_status && <Button title={busy ? "Saving…" : `Mark ${label(row.next_status)}`} disabled={busy} onPress={() => act("status", { status: row.next_status }, "PATCH")} />}{eligible && <RiderEvidence token={token} id={row.id} />}{eligible && <View><View style={s.row}><Text style={s.body}>Share live location</Text><Switch accessibilityLabel="Share live delivery location" value={sharing} onValueChange={toggleSharing} /></View><Text style={s.muted}>Sharing continues in the background for this active job, for up to 8 hours. Stop sharing here. Force-closing the app may stop updates.</Text>{!!locationStatus && <Text style={s.muted}>{locationStatus}</Text>}</View>}{row.status === "out_for_delivery" && <><Input title="Customer’s 6-digit delivery OTP" numeric value={otp} onChange={setOtp} />{row.payment_method === "cod" && <View style={s.row}><Text style={s.body}>Collected {money(row.collection_amount)} cash</Text><Switch accessibilityLabel="Confirm cash collected" value={cash} onValueChange={setCash} /></View>}<Button title={busy ? "Completing…" : "Complete delivery"} disabled={busy || !/^\d{6}$/.test(otp) || (row.payment_method === "cod" && !cash)} onPress={() => act("complete", { otp, cash_collected: cash })} /></>}</>}</View>;
}

export default function PartnerWorkspace({ token, mode, onClose, target }: { token: string; mode: "seller" | "rider"; onClose: () => void; target?: NotificationTarget | null }) {
  const [role, setRole] = useState<Role | null>(null);
  const [form, setForm] = useState<{ path: string; title: string } | null>(null);
  const [colorProduct, setColorProduct] = useState<{
  id: number;
  name: string;
  } | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<{ kind: Kind; id: number } | null>(null);
  const [section, setSection] = useState(mode === "seller" ? "orders" : "active");
  const [kind, setKind] = useState<Kind>(["shop", "food", "grocery"].includes(target?.kind || "") ? target!.kind as Kind : "shop");
  const [rows, setRows] = useState<(SellerOrder | Listing | Payout | Job)[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pageNumber, setPageNumber] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const generation = useRef(0);
  const load = useCallback(async (pageNum = 1) => {
    const current = ++generation.current;
    setLoading(true); setError("");
    if (pageNum === 1) setRows([]);
    try {
      const roles = await partnerRequest<Roles>(token, "roles/");
      if (current !== generation.current) return;
      const currentRole = roles[mode]; setRole(currentRole);
      if (currentRole?.status !== "approved") return;
      if (mode === "seller") {
        const info = await partnerRequest<Workspace>(token, "seller/");
        if (current !== generation.current) return;
        setWorkspace(info);
        const allowed = info.allowed_kinds || [];
        if (!allowed.length) { setRows([]); setHasMore(false); return; }
        if (!allowed.includes(kind)) { setRows([]); setHasMore(false); setKind(allowed[0]); return; }
      }
      const path = mode === "seller" ? `seller/${kind}/${section}/?page=${pageNum}${section === "orders" ? "&grouped=1" : ""}${target?.order_id && target.kind === kind && section === "orders" ? `&order_id=${target.order_id}` : ""}` : section === "earnings" ? `rider/earnings/?page=${pageNum}` : `rider/jobs/?scope=${section}&page=${pageNum}${target?.delivery_id ? `&delivery_id=${target.delivery_id}` : ""}`;
      const result = await partnerRequest<Page<SellerOrder | Listing | Payout | Job>>(token, path);
      if (current !== generation.current) return;
      setRows(prev => pageNum === 1 ? result.results : [...prev, ...result.results]);
      setHasMore(!!result.next); setPageNumber(pageNum);
    } catch (err) { if (current === generation.current) setError(err instanceof Error ? err.message : "Unable to load workspace."); }
    finally { if (current === generation.current) setLoading(false); }
  }, [token, mode, kind, section, target]);
  useEffect(() => { load(); return () => { generation.current++; }; }, [load]);
  const changeAvailability = async (value: boolean, storeKind?: Kind) => {
    if (busy) return;
    setBusy(true);
    try { await partnerRequest(token, storeKind ? `seller/${storeKind}/availability/` : "rider/online/", "PATCH", storeKind ? { accepts_orders: value } : { is_online: value }); await load(); } catch (err) { fail(err); } finally { setBusy(false); }
  };
 const approved = role?.status === "approved";
 const categoryReady = mode !== "seller" || !!workspace?.allowed_kinds?.includes(kind);

return (
  <Modal visible animationType="slide" onRequestClose={onClose}>
    <SafeAreaView style={s.screen}>
      <View style={s.header}>
        <View>
          <Text style={s.eyebrow}>ZIYAMART PARTNERS</Text>
          <Text style={s.title}>
            {mode === "seller" ? "Seller Center" : "Rider workspace"}
          </Text>
        </View>

        <Button secondary title="Close" onPress={onClose} />
      </View>

      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={() => load()}
          />
        }
        keyboardShouldPersistTaps="handled"
      >
        <Text style={s.body}>
          {role?.name || "Your partner account"}
        </Text>

        {role && (
          <Button
            secondary
            title="Set up payout account"
            onPress={() =>
              setForm({
                path: `payout-setup/${mode}/`,
                title: "Payout account",
              })
            }
          />
        )}

        {!role && !loading && !error && (
          <Button
            title={
              mode === "seller"
                ? "Apply as a seller"
                : "Apply as a rider"
            }
            onPress={() =>
              setForm({
                path: `applications/${mode}/`,
                title:
                  mode === "seller"
                    ? "Seller application"
                    : "Rider application",
              })
            }
          />
        )}

        {approved &&
          categoryReady &&
          mode === "seller" &&
          section === "catalog" && (
            <Button
              title="Add product"
              onPress={() =>
                setForm({
                  path:
                    kind === "shop"
                      ? "seller/products/new/"
                      : `seller/${kind}/products/new/`,
                  title: "New product",
                })
              }
            />
          )}

        {!!error && (
          <View style={s.card}>
            <Text accessibilityRole="alert" style={s.error}>
              {error}
            </Text>

            <Button title="Retry" onPress={() => load()} />
          </View>
        )}

        {loading && rows.length === 0 && (
          <ActivityIndicator color="#EF6C35" size="large" />
        )}

        {!loading && !approved && !error && (
          <View style={s.card}>
            <Text style={s.cardTitle}>
              {role
                ? `Application ${role.status}`
                : `No ${mode} profile yet`}
            </Text>

            <Text style={s.muted}>
              {role
                ? "Marketplace approval is required before you can manage orders or deliveries. Pull down to check your status."
                : "Your account is not registered for this role yet. Apply to join the marketplace team."}
            </Text>
          </View>
        )}

        {approved && mode === "seller" && workspace && !workspace.allowed_kinds?.length && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Complete your selling category</Text>
            <Text style={s.muted}>Contact support to confirm what you sell on your seller registration. Your category tools will appear here once it is updated.</Text>
          </View>
        )}

        {approved && categoryReady && (
          <>
            {mode === "seller" && kind !== "shop" && (
              <Button
                secondary
                title="Store setup & settings"
                onPress={() =>
                  setForm({
                    path: `seller/${kind}/store/`,
                    title: "Store settings",
                  })
                }
              />
            )}

            {mode === "seller" ? (
              <>
                <Text style={s.muted}>
                  {workspace?.payouts_enabled
                    ? `Payouts enabled · Bank ending ${workspace.bank_last4}`
                    : "Payouts await verified bank details and marketplace approval."}
                </Text>

                {Number(workspace?.return_balance || 0) > 0 && (
                  <Text style={s.cash}>
                    Outstanding return balance:{" "}
                    {money(workspace!.return_balance)}
                  </Text>
                )}

                {workspace?.stores.map(store => (
                  <View key={store.kind} style={s.row}>
                    <Text style={s.body}>
                      {store.name} ·{" "}
                      {store.accepts_orders ? "Open" : "Paused"}
                    </Text>

                    <Switch
                      disabled={busy}
                      accessibilityLabel={`Accept orders for ${store.name}`}
                      value={store.accepts_orders}
                      onValueChange={value =>
                        changeAvailability(value, store.kind)
                      }
                    />
                  </View>
                ))}

                <View style={s.wrap}>
                  {(workspace?.allowed_kinds || []).map(
                    value => (
                      <Button
                        key={value}
                        secondary={kind !== value}
                        title={
                          value === "shop"
                            ? workspace?.business_category || "Merchandise"
                            : label(value)
                        }
                        onPress={() => setKind(value)}
                      />
                    )
                  )}
                </View>
              </>
            ) : (
              <View style={s.row}>
                <Text style={s.body}>
                  {role.is_online
                    ? "Online · accepting jobs"
                    : "Offline"}{" "}
                  · {role.pincode}
                </Text>

                <Switch
                  accessibilityLabel="Go online for delivery jobs"
                  value={!!role.is_online}
                  disabled={busy}
                  onValueChange={value =>
                    changeAvailability(value)
                  }
                />
              </View>
            )}

            <View style={s.wrap}>
              {(mode === "seller"
                ? ["orders", "catalog", "payouts"]
                : [
                    "active",
                    "available",
                    "history",
                    "earnings",
                  ]
              ).map(value => (
                <Button
                  key={value}
                  secondary={section !== value}
                  title={label(value)}
                  onPress={() => setSection(value)}
                />
              ))}
            </View>

            {!loading &&
              !error &&
              rows.length === 0 && (
                <View style={s.card}>
                  <Text style={s.cardTitle}>
                    No {label(section)} to show
                  </Text>

                  <Text style={s.muted}>
                    {section === "available"
                      ? "Go online to see available jobs in your delivery pincode."
                      : "Pull down to refresh as new activity arrives."}
                  </Text>
                </View>
              )}

            {rows.map(row =>
              mode === "seller" ? (
                section === "orders" ? (
                  <SellerOrderRow
                    key={`${kind}-${row.id}`}
                    order={row as SellerOrder}
                    onOpen={() => setSelectedOrder({ kind, id: (row as SellerOrder).order_id })}
                  />
                ) : section === "catalog" ? (
                  <ListingCard
                    key={`${kind}-${row.id}`}
                    row={row as Listing}
                    kind={kind}
                    token={token}
                    refresh={() => load()}
                    edit={() =>
                      setForm({
                        path:
                          kind === "shop"
                            ? `seller/products/${row.id}/edit/`
                            : `seller/${kind}/products/${row.id}/edit/`,
                        title: "Edit product",
                      })
                    }
                    manageColors={() =>
                      setColorProduct({
                        id: row.id,
                        name: (row as Listing).name,
                      })
                    }
                    variant={id =>
                      setForm({
                        path: `seller/${kind}/products/${row.id}/variants/${id ?? "new"}/`,
                        title: "Product variant",
                      })
                    }
                  />
                ) : (
                  <PayoutCard
                    key={row.id}
                    row={row as Payout}
                  />
                )
              ) : section === "earnings" ? (
                <PayoutCard
                  key={row.id}
                  row={row as Payout}
                />
              ) : (
                <JobCard
                  key={`${section}-${row.id}`}
                  row={row as Job}
                  token={token}
                  active={section === "active"}
                  refresh={() => load()}
                />
              )
            )}

            {hasMore && (
              <Button
                secondary
                title={loading ? "Loading…" : "Load more"}
                disabled={loading}
                onPress={() => load(pageNumber + 1)}
              />
            )}
          </>
        )}
      </ScrollView>

      {selectedOrder && <SellerOrderDetail token={token} kind={selectedOrder.kind} orderId={selectedOrder.id} onClose={() => setSelectedOrder(null)} onChanged={() => load()} />}
      {form && (
        <PartnerForm
          token={token}
          path={form.path}
          title={form.title}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            load();
          }}
        />
      )}
      {colorProduct && (
  <ProductColors
    token={token}
    productId={colorProduct.id}
    productName={colorProduct.name}
    onClose={() => setColorProduct(null)}
    onChanged={() => load()}
  />
)}
    </SafeAreaView>
  </Modal>
);
}
const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFF8EF" }, header: { padding: 18, flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderBottomWidth: 1, borderColor: "#E9E2D8" },
  eyebrow: { color: "#B04B1F", fontSize: 11, fontWeight: "800", letterSpacing: 1.5 }, title: { color: "#17243A", fontSize: 24, fontWeight: "800" }, content: { padding: 18, gap: 14, paddingBottom: 40 },
  card: { backgroundColor: "white", padding: 18, borderRadius: 18, borderWidth: 1, borderColor: "#E9E2D8", gap: 10 }, cardTitle: { color: "#17243A", fontSize: 18, fontWeight: "700", flexShrink: 1 },
  body: { color: "#17243A", fontSize: 15, flexShrink: 1 }, muted: { color: "#5D6B7D", fontSize: 13, lineHeight: 20 }, badge: { color: "#0A765C", fontSize: 13, fontWeight: "700", textTransform: "capitalize" },
  amount: { color: "#17243A", fontSize: 23, fontWeight: "800" }, cash: { color: "#9A4813", backgroundColor: "#FFF0D1", padding: 10, borderRadius: 8, fontWeight: "700" }, error: { color: "#B32929", lineHeight: 21 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }, wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: { backgroundColor: "#C84E1F", borderRadius: 12, paddingHorizontal: 15, paddingVertical: 13, minHeight: 44, alignItems: "center" }, buttonText: { color: "white", fontWeight: "700", textTransform: "capitalize" }, secondary: { backgroundColor: "#F2EDE5" }, secondaryText: { color: "#17243A" }, disabled: { opacity: 0.45 },
  field: { gap: 5 }, input: { borderWidth: 1, borderColor: "#C7CFD8", padding: 12, borderRadius: 10, color: "#17243A", backgroundColor: "white", minHeight: 46 }, variant: { gap: 8, borderTopWidth: 1, borderColor: "#E9E2D8", paddingTop: 12 },
});
