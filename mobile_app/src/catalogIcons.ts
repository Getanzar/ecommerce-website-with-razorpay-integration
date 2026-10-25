/** Native category symbols, also covering legacy category names. */
export function categorySymbol(name: string): string {
  const value = name.toLowerCase();
  if (/accessor|cover|case/.test(value) && /phone|mobile/.test(value)) return "🎧";
  if (/electronics/.test(value)) return "🔌";
  if (/mobile|phone/.test(value)) return "📱";
  if (/laptop/.test(value)) return "💻";
  if (/\btv\b|television/.test(value)) return "📺";
  if (/appliance/.test(value)) return "🏠";
  if (/clean|bathroom/.test(value)) return "🧹";
  if (/shoe|footwear/.test(value)) return "👟";
  if (/women|dress|suit/.test(value)) return "👗";
  if (/kids|children|baby/.test(value)) return "🧸";
  if (/men|shirt|clothing/.test(value)) return "👕";
  if (/grocery|food/.test(value)) return "🛒";
  if (/accessor/.test(value)) return "👜";
  return "🛍️";
}
