// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/**
 * @title MaintenanceRecordNFT (Mieie 見える家プロジェクト プロトタイプ)
 * @notice 建物メンテナンス記録(PDF報告書)のSHA-256ハッシュをNFTとして刻印する。
 *         記録は建物と不可分であるべきという思想から、譲渡機能を持たない
 *         「ソウルバウンド(譲渡不可)」型のERC-721。
 */
contract MaintenanceRecordNFT {
    string public constant name = "Mieie Maintenance Record";
    string public constant symbol = "MIEIE";

    address public immutable registrar; // 記録者(建築士事務所)
    uint256 public nextTokenId;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => string) private _tokenURIs;

    /// tokenId => 報告書PDFのSHA-256ハッシュ
    mapping(uint256 => bytes32) public documentHash;
    /// tokenId => 記録時刻(ブロックタイムスタンプ)
    mapping(uint256 => uint256) public recordedAt;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event RecordMinted(
        uint256 indexed tokenId,
        bytes32 documentHash,
        string propertyId,
        uint256 timestamp
    );

    constructor() {
        registrar = msg.sender;
    }

    /// @notice メンテナンス記録を刻印(ミント)する
    /// @param _docHash 報告書PDFのSHA-256ハッシュ
    /// @param _tokenURI メタデータ(data URI形式でオンチェーン格納)
    /// @param _propertyId 物件識別子(例: "府中市〇〇町 S邸")
    function mintRecord(
        bytes32 _docHash,
        string calldata _tokenURI,
        string calldata _propertyId
    ) external returns (uint256) {
        require(msg.sender == registrar, "registrar only");
        uint256 tokenId = ++nextTokenId;
        _owners[tokenId] = msg.sender;
        _balances[msg.sender] += 1;
        _tokenURIs[tokenId] = _tokenURI;
        documentHash[tokenId] = _docHash;
        recordedAt[tokenId] = block.timestamp;
        emit Transfer(address(0), msg.sender, tokenId);
        emit RecordMinted(tokenId, _docHash, _propertyId, block.timestamp);
        return tokenId;
    }

    /// @notice 手元のPDFのハッシュがチェーン上の記録と一致するか検証
    function verify(uint256 tokenId, bytes32 hash) external view returns (bool) {
        require(_owners[tokenId] != address(0), "no such token");
        return documentHash[tokenId] == hash;
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        address o = _owners[tokenId];
        require(o != address(0), "no such token");
        return o;
    }

    function balanceOf(address a) external view returns (uint256) {
        return _balances[a];
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0), "no such token");
        return _tokenURIs[tokenId];
    }

    function totalSupply() external view returns (uint256) {
        return nextTokenId;
    }

    function supportsInterface(bytes4 id) external pure returns (bool) {
        return id == 0x80ac58cd || id == 0x5b5e139f || id == 0x01ffc9a7;
    }
}
