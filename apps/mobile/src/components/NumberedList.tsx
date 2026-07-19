import { StyleSheet, Text, View } from 'react-native';

type NumberedListProps = {
  items: string[];
  emptyText?: string;
};

export function NumberedList({ items, emptyText = '暂无' }: NumberedListProps) {
  const rows = items.map((item) => item.trim()).filter(Boolean);

  if (!rows.length) {
    return <Text style={styles.empty}>{emptyText}</Text>;
  }

  return (
    <View style={styles.list}>
      {rows.map((item, index) => (
        <View key={`${index}-${item}`} style={styles.row}>
          <Text style={styles.index}>{index + 1}、</Text>
          <Text style={styles.text}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  empty: {
    color: '#8b95a7',
    fontSize: 13,
    lineHeight: 22,
  },
  index: {
    color: '#6657ff',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 22,
    width: 30,
  },
  list: {
    gap: 10,
  },
  row: {
    alignItems: 'flex-start',
    flexDirection: 'row',
  },
  text: {
    color: '#374151',
    flex: 1,
    fontSize: 13,
    lineHeight: 22,
  },
});
