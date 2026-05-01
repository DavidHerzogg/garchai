/**
 * GARCH AI — Login Illustration
 * Uses SvgUri + expo-asset to load illustration.svg from the assets folder.
 * No inline embedding — avoids token / bundle-size issues.
 */
import React, { useEffect, useState } from 'react';
import { View } from 'react-native';
import { SvgUri } from 'react-native-svg';
import { Asset } from 'expo-asset';

interface Props {
  width?: number | string;
  height?: number | string;
}

export default function IllustrationSvg({ width = '100%', height = 300 }: Props) {
  const [uri, setUri] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [asset] = await Asset.loadAsync(
        require('@/assets/images/illustration.svg')
      );
      if (!cancelled) setUri(asset.localUri ?? asset.uri);
    })();
    return () => { cancelled = true; };
  }, []);

  if (!uri) return <View style={{ width: typeof width === 'number' ? width : '100%', height: typeof height === 'number' ? height : 300 }} />;

  return <SvgUri uri={uri} width={width} height={height} />;
}
