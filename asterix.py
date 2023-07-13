from xml.dom import minidom

filenames = {
    1: 'config/asterix_cat001_1_1.xml',
    2: 'config/asterix_cat002_1_0.xml',
    8: 'config/asterix_cat008_1_0.xml',
    10: 'config/asterix_cat010_1_1.xml',
    11: 'config/asterix_cat011_1_2.xml',
    19: 'config/asterix_cat019_1_2.xml',
    20: 'config/asterix_cat020_1_7.xml',
    21: 'config/asterix_cat021_1_8.xml',
    23: 'config/asterix_cat023_1_2.xml',
    30: 'config/asterix_cat030_6_2.xml',
    31: 'config/asterix_cat031_6_2.xml',
    32: 'config/asterix_cat032_7_0.xml',
    48: 'config/asterix_cat048_1_14.xml',
    62: 'config/asterix_cat062_1_16.xml',
    63: 'config/asterix_cat063_1_3.xml',
    65: 'config/asterix_cat065_1_3.xml',
    242: 'config/asterix_cat242_1_0.xml',
    252: 'config/asterix_cat252_7_0.xml'
}

class AsterixDecoder:
    def __init__(self, hexstr):
        if len(hexstr) % 2 != 0:
            hexstr = '0' + hexstr
        bytesdata = bytearray.fromhex(hexstr)
        self.bytes = bytesdata
        self.length = len(self.bytes)
        self.p = 0
        self.decoded_result = {}

        # Decode ASTERIX category from the first byte
        cat = int.from_bytes(self.bytes[0:1], byteorder='big', signed=True)
        print(cat)
        self.p += 1

        try:
            self.cat = minidom.parse(filenames[cat])
            category = self.cat.getElementsByTagName('Category')[0]
            self.dataitems = category.getElementsByTagName('DataItem')
            uap = category.getElementsByTagName('UAP')[0]
            self.uapitems = uap.getElementsByTagName('UAPItem')
        except:
            print('Cat %d not supported.' % cat)
            return

        self.decoded_result[cat] = []

        while self.p < self.length:
            self.decoded = {}
            self.decode()
            self.decoded_result[cat].append(self.decoded)

    def get_result(self):
        return self.decoded_result

    def decode(self):
        fspec_octets = 0
        fspec_octets_len = 0
        while True:
            if self.p >= self.length:  # Check if reached the end of the bytes
                break

            _b = self.bytes[self.p]
            self.p += 1
            fspec_octets = (fspec_octets << 8) + _b
            fspec_octets_len += 1
            if _b & 1 == 0:
                break

        itemids = []
        mask = 1 << (8 * fspec_octets_len - 1)

        for i in range(0, 8 * fspec_octets_len):
            if fspec_octets & mask > 0:
                itemid = self.uapitems[i].firstChild.nodeValue
                if itemid != '-':
                    itemids.append(itemid)
            mask >>= 1

        for itemid in itemids:
            for dataitem in self.dataitems:
                if dataitem.getAttribute('id') == itemid:
                    dataitemformat = dataitem.getElementsByTagName('DataItemFormat')[0]
                    for cn in dataitemformat.childNodes:
                        r = None
                        if cn.nodeName == 'Fixed':
                            r = self.decode_fixed(cn)
                        elif cn.nodeName == 'Repetitive':
                            r = self.decode_repetitive(cn)
                        elif cn.nodeName == 'Variable':
                            r = self.decode_variable(cn)
                        elif cn.nodeName == 'Compound':
                            r = self.decode_compound(cn)

                        if r:
                            self.decoded.update({itemid: r})

    def decode_fixed(self, datafield):
        results = {}
        length = int(datafield.getAttribute('length'))
        bitslist = datafield.getElementsByTagName('Bits')

        _bytes = self.bytes[self.p: self.p + length]
        self.p += length

        data = int.from_bytes(_bytes, byteorder='big', signed=False)

        for bits in bitslist:
            bit_name = bits.getElementsByTagName('BitsShortName')[0].firstChild.nodeValue

            bit = bits.getAttribute('bit')
            if bit != '':
                bit = int(bit)
                results[bit_name] = ((data >> (bit - 1)) & 1)
            else:
                from_ = int(bits.getAttribute('from'))
                to_ = int(bits.getAttribute('to'))

                if from_ < to_:
                    from_, to_ = to_, from_
                mask = (1 << (from_ - to_ + 1)) - 1
                results[bit_name] = ((data >> (to_ - 1)) & mask)

                if bits.getAttribute('encode') == 'signed':
                    if results[bit_name] & (1 << (from_ - to_)):
                        results[bit_name] = -(1 << (from_ - to_ + 1)) + results[bit_name]

                BitsUnit = bits.getElementsByTagName("BitsUnit")
                if BitsUnit:
                    scale = BitsUnit[0].getAttribute('scale')
                    results[bit_name] = results[bit_name] * float(scale)

        return results

    def decode_variable(self, datafield):
        results = {}
        consumed_length = 0

        for fixed in datafield.getElementsByTagName('Fixed'):
            r = self.decode_fixed(fixed)
            results.update(r)
            assert 'FX' in r
            if r['FX'] == 0:
                break

            # Track the consumed length
            consumed_length += int(fixed.getAttribute('length'))

        return results, consumed_length

    def decode_repetitive(self, datafield):
        if self.p >= self.length:
            return []  # No more bytes to decode

        rep = self.bytes[self.p]
        self.p += 1

        results = []
        fixed_elements = datafield.getElementsByTagName('Fixed')

        if len(fixed_elements) == 0:
            return results

        fixed = fixed_elements[0]
        for i in range(min(rep, self.length - self.p + 1)):
            r = self.decode_fixed(fixed)
            results.append(r)

        return results

    def decode_compound(self, datafield):
        indicator_octets = 0
        indicator_octets_len = 0
        while True:
            if self.p >= self.length:  # Check if reached the end of the bytes
                break

            _b = self.bytes[self.p]
            self.p += 1
            indicator_octets = (indicator_octets << 8) + _b
            indicator_octets_len += 1

            if _b & 1 == 0:
                break

        indicators = []
        mask = 1 << (8 * indicator_octets_len - 1)
        indicator = 1
        for i in range(0, 8 * indicator_octets_len):
            if i % 8 != 7:
                continue

            if indicator_octets & (mask >> i) > 0:
                indicators.append(indicator)

            indicator += 1

        results = {}
        index = 0
        for cn in datafield.childNodes:
            if cn.nodeName not in ['Fixed', 'Repetitive', 'Variable', 'Compound']:
                continue

            if index not in indicators:
                index += 1
                continue

            if cn.nodeName == 'Fixed':
                r = self.decode_fixed(cn)
            elif cn.nodeName == 'Repetitive':
                r = self.decode_repetitive(cn)
            elif cn.nodeName == 'Variable':
                r = self.decode_variable(cn)
            elif cn.nodeName == 'Compound':
                r = self.decode_compound(cn)

            index += 1
            results.update(r)

        return results

if __name__ == '__main__':

    hexstr = '15004EFF9FB35B83E40001080001014CFBA315CD2A4A0EAF0AE69555250757D74CFB330005554CFBA31189374B4CFB3319CAC08341C60A00500C000000F500004CFBB3414175D75820006A06D901'
    decoder = AsterixDecoder(hexstr)
    decoded_result = decoder.get_result()
    print("Decoded Result:", decoded_result)
