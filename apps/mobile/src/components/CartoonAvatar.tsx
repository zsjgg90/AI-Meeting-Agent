import { StyleSheet, View } from 'react-native';

type Props = {
  size?: number;
  showQuestion?: boolean;
};

export function CartoonAvatar({ size = 76, showQuestion = false }: Props) {
  const faceSize = Math.round(size * 0.55);
  const hairWidth = Math.round(size * 0.55);
  const hairHeight = Math.round(size * 0.28);

  return (
    <View style={[styles.wrap, { height: size, width: size, borderRadius: size / 2 }]}>
      <View style={[styles.hair, { height: hairHeight, width: hairWidth, borderRadius: hairHeight }]} />
      <View style={[styles.face, { height: faceSize, width: faceSize, borderRadius: faceSize / 2 }]}>
        <View style={styles.eyes}>
          <View style={styles.eye} />
          <View style={styles.eye} />
        </View>
        <View style={styles.smile} />
      </View>
      <View style={[styles.hoodie, { width: Math.round(size * 0.72), height: Math.round(size * 0.34) }]} />
      {showQuestion ? <View style={styles.questionDot} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    backgroundColor: '#eeeaff',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  hair: {
    backgroundColor: '#35205e',
    position: 'absolute',
    top: '14%',
    zIndex: 3,
  },
  face: {
    alignItems: 'center',
    backgroundColor: '#ffcfa8',
    justifyContent: 'center',
    marginTop: '12%',
    zIndex: 2,
  },
  eyes: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 7,
  },
  eye: {
    backgroundColor: '#111827',
    borderRadius: 3,
    height: 5,
    width: 5,
  },
  smile: {
    borderBottomColor: '#a35353',
    borderBottomWidth: 2,
    borderRadius: 8,
    height: 8,
    width: 18,
  },
  hoodie: {
    backgroundColor: '#6c4dff',
    borderTopLeftRadius: 999,
    borderTopRightRadius: 999,
    bottom: -4,
    position: 'absolute',
  },
  questionDot: {
    backgroundColor: '#ffffff',
    borderColor: '#6c4dff',
    borderRadius: 7,
    borderWidth: 3,
    height: 14,
    position: 'absolute',
    right: 7,
    top: 9,
    width: 14,
  },
});
