
/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
DROP TABLE IF EXISTS `department`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `department` (
  `DepartmentID` int NOT NULL COMMENT 'Unique identifier for a department ',
  `DepartmentName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of department ',
  PRIMARY KEY (`DepartmentID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `grn`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `grn` (
  `GRNID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for the GRN ',
  `PurchaseID` int NOT NULL COMMENT 'Purchase being received; one GRN at most per purchase',
  `GRNNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Unique GRN document number ',
  `GRNDate` date NOT NULL COMMENT 'Date the goods were received ',
  `StaffID` int NOT NULL COMMENT 'Staff member who received the goods ',
  `Remarks` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Additional information about the delivery ',
  PRIMARY KEY (`GRNID`),
  UNIQUE KEY `GRNNumber` (`GRNNumber`),
  UNIQUE KEY `PurchaseID` (`PurchaseID`),
  KEY `StaffID` (`StaffID`),
  CONSTRAINT `grn(goods_received_note)\_ibfk_1` FOREIGN KEY (`PurchaseID`) REFERENCES `purchase` (`PurchaseID`),
  CONSTRAINT `grn(goods_received_note)\_ibfk_2` FOREIGN KEY (`StaffID`) REFERENCES `staff` (`StaffID`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `item`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `item` (
  `ItemID` int NOT NULL COMMENT 'Unique identifier for each item ',
  `ItemName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of item ',
  `UnitID` int NOT NULL COMMENT 'Unit of item measurement; references UNIT(UnitID) ',
  `Quantity` int NOT NULL COMMENT 'Current quantity of item in stock ',
  `ReorderLevel` int NOT NULL COMMENT 'Minimum stock level before reordering ',
  `StoreID` int NOT NULL COMMENT 'Identifies the store where the item belongs ',
  `IsArchived` tinyint(1) NOT NULL,
  `ArchivedBy` int DEFAULT NULL,
  `ArchivedAt` datetime(6) DEFAULT NULL,
  `ArchiveReason` longtext COLLATE utf8mb4_general_ci,
  `AuditHistory` json DEFAULT NULL,
  PRIMARY KEY (`ItemID`),
  KEY `item_ibfk_1` (`UnitID`),
  KEY `StoreID` (`StoreID`),
  KEY `fk_item_archived_by_staff` (`ArchivedBy`),
  CONSTRAINT `fk_item_archived_by_staff` FOREIGN KEY (`ArchivedBy`) REFERENCES `staff` (`StaffID`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `item_ibfk_1` FOREIGN KEY (`UnitID`) REFERENCES `unit` (`UnitID`),
  CONSTRAINT `item_ibfk_2` FOREIGN KEY (`StoreID`) REFERENCES `store` (`StoreID`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `position`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `position` (
  `PositionID` int NOT NULL COMMENT 'Unique identifier for a position ',
  `PositionName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of staff position ',
  PRIMARY KEY (`PositionID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `purchase`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `purchase` (
  `PurchaseID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for each purchase made ',
  `StoreID` int NOT NULL COMMENT 'Store for which the purchase is made; references STORE ',
  `SupplierID` int NOT NULL COMMENT 'Supplier who provided the purchase ',
  `StaffID` int NOT NULL COMMENT 'Staff member responsible for the purchase ',
  `InvoiceNumber` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Unique number on the supplier’s invoice ',
  `InvoiceDate` date NOT NULL COMMENT 'Date on supplier invoice ',
  `PurchaseDate` date NOT NULL COMMENT 'Date on which the purchase was made ',
  `TotalAmount` decimal(12,3) NOT NULL COMMENT 'Total monetary value of the purchase ',
  `TransactionType` varchar(12) COLLATE utf8mb4_general_ci NOT NULL,
  `ParentPurchaseID` int DEFAULT NULL,
  `OrderNumber` varchar(30) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `OrderStatus` varchar(20) COLLATE utf8mb4_general_ci NOT NULL,
  `ApprovedBy` int DEFAULT NULL,
  `ExpectedDate` date DEFAULT NULL,
  `Notes` longtext COLLATE utf8mb4_general_ci NOT NULL,
  `RejectionReason` longtext COLLATE utf8mb4_general_ci NOT NULL,
  PRIMARY KEY (`PurchaseID`),
  UNIQUE KEY `InvoiceNumber` (`InvoiceNumber`),
  UNIQUE KEY `OrderNumber` (`OrderNumber`),
  KEY `StoreID` (`StoreID`),
  KEY `SupplierID` (`SupplierID`),
  KEY `StaffID` (`StaffID`),
  KEY `purchase_ParentPurchaseID_7eb161aa_fk_purchase_PurchaseID` (`ParentPurchaseID`),
  KEY `fk_purchase_approved_by_staff` (`ApprovedBy`),
  CONSTRAINT `fk_purchase_approved_by_staff` FOREIGN KEY (`ApprovedBy`) REFERENCES `staff` (`StaffID`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `purchase_ibfk_1` FOREIGN KEY (`StoreID`) REFERENCES `store` (`StoreID`),
  CONSTRAINT `purchase_ibfk_2` FOREIGN KEY (`SupplierID`) REFERENCES `supplier` (`SupplierID`),
  CONSTRAINT `purchase_ibfk_3` FOREIGN KEY (`StaffID`) REFERENCES `staff` (`StaffID`),
  CONSTRAINT `purchase_ParentPurchaseID_7eb161aa_fk_purchase_PurchaseID` FOREIGN KEY (`ParentPurchaseID`) REFERENCES `purchase` (`PurchaseID`)
) ENGINE=InnoDB AUTO_INCREMENT=20 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `purchase_item`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `purchase_item` (
  `PurchaseItemID` int NOT NULL COMMENT 'Unique identifier for a purchase line ',
  `PurchaseID` int NOT NULL COMMENT 'Purchase to which the item belongs ',
  `ItemID` int NOT NULL COMMENT 'Item being purchased ',
  `UnitCost` decimal(12,2) NOT NULL COMMENT 'Cost of one unit of the item ',
  `Quantity` int NOT NULL COMMENT 'Number of purchased units ',
  `Subtotal` decimal(12,2) GENERATED ALWAYS AS ((`UnitCost` * `Quantity`)) STORED COMMENT 'Total cost for the purchase line (UnitCost × Quantity)',
  KEY `PurchaseID` (`PurchaseID`),
  KEY `ItemID` (`ItemID`),
  CONSTRAINT `purchase_item_ibfk_1` FOREIGN KEY (`PurchaseID`) REFERENCES `purchase` (`PurchaseID`),
  CONSTRAINT `purchase_item_ibfk_2` FOREIGN KEY (`ItemID`) REFERENCES `item` (`ItemID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `request`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `request` (
  `RequestID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for each request',
  `StoreID` int NOT NULL COMMENT 'Store for which the request is made; references STORE ',
  `StaffID` int NOT NULL COMMENT 'Staff member who made the request ',
  `RequestDate` date NOT NULL COMMENT 'Date on which request was made ',
  `StatusID` int NOT NULL COMMENT 'Current status of request; references STATUS ',
  `ApprovedBy` int DEFAULT NULL,
  `DecisionReason` longtext COLLATE utf8mb4_general_ci NOT NULL,
  `DecidedAt` datetime(6) DEFAULT NULL,
  `LegacyReviewReason` longtext COLLATE utf8mb4_general_ci NOT NULL,
  `LegacyReviewedBy` int DEFAULT NULL,
  `LegacyReviewedAt` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`RequestID`),
  KEY `StoreID` (`StoreID`),
  KEY `StaffID` (`StaffID`),
  KEY `StatusID` (`StatusID`),
  KEY `ApprovedBy` (`ApprovedBy`),
  KEY `fk_request_legacy_reviewed_by_staff` (`LegacyReviewedBy`),
  CONSTRAINT `fk_request_legacy_reviewed_by_staff` FOREIGN KEY (`LegacyReviewedBy`) REFERENCES `staff` (`StaffID`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `request_ibfk_1` FOREIGN KEY (`StoreID`) REFERENCES `store` (`StoreID`),
  CONSTRAINT `request_ibfk_2` FOREIGN KEY (`StaffID`) REFERENCES `staff` (`StaffID`),
  CONSTRAINT `request_ibfk_3` FOREIGN KEY (`StatusID`) REFERENCES `status` (`StatusID`),
  CONSTRAINT `request_ibfk_4` FOREIGN KEY (`ApprovedBy`) REFERENCES `staff` (`StaffID`)
) ENGINE=InnoDB AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `request_item`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `request_item` (
  `RequestItemID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for a requested item',
  `RequestID` int NOT NULL COMMENT 'Request to which the item belongs ',
  `ItemID` int NOT NULL COMMENT 'Item being requested ',
  `QtyRequested` int NOT NULL COMMENT 'Quantity requested by the staff member ',
  `QtyIssued` int NOT NULL COMMENT 'Quantity actually issued ',
  `QtyApproved` int DEFAULT NULL,
  PRIMARY KEY (`RequestItemID`),
  KEY `RequestID` (`RequestID`),
  KEY `ItemID` (`ItemID`),
  CONSTRAINT `request_item_ibfk_1` FOREIGN KEY (`RequestID`) REFERENCES `request` (`RequestID`),
  CONSTRAINT `request_item_ibfk_2` FOREIGN KEY (`ItemID`) REFERENCES `item` (`ItemID`)
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `staff`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `staff` (
  `StaffID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for each staff member ',
  `SurName` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Surname of a staff member',
  `OtherNames` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Staff member’s other names ',
  `DepartmentID` int NOT NULL COMMENT 'Department where staff member belongs; references DEPARTMENT ',
  `PositionID` int NOT NULL COMMENT 'Staff member’s position; references position',
  `Contact` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT ' Staff member’s contact ',
  `Email` varchar(254) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `PasswordHash` varchar(256) COLLATE utf8mb4_general_ci NOT NULL DEFAULT '!',
  `IsActive` tinyint(1) NOT NULL DEFAULT '1',
  `SetupTokenHash` char(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `SetupTokenExpiresAt` datetime DEFAULT NULL,
  `SessionTokenHash` char(64) COLLATE utf8mb4_general_ci DEFAULT NULL,
  `SessionExpiresAt` datetime DEFAULT NULL,
  PRIMARY KEY (`StaffID`),
  UNIQUE KEY `Email` (`Email`),
  KEY `DepartmentID` (`DepartmentID`),
  KEY `PositionID` (`PositionID`),
  CONSTRAINT `staff_ibfk_1` FOREIGN KEY (`DepartmentID`) REFERENCES `department` (`DepartmentID`),
  CONSTRAINT `staff_ibfk_2` FOREIGN KEY (`PositionID`) REFERENCES `position` (`PositionID`)
) ENGINE=InnoDB AUTO_INCREMENT=79 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `status` (
  `StatusID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for a request status ',
  `StatusName` varchar(30) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of the request status ',
  PRIMARY KEY (`StatusID`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `store`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `store` (
  `StoreID` int NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for each store ',
  `StoreName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of store ',
  PRIMARY KEY (`StoreID`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `supplier`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `supplier` (
  `SupplierID` int NOT NULL COMMENT 'Unique identifier for each supplier ',
  `SupplierName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of supplier ',
  `Contact` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Supplier contact number ',
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT 'Supplier email address ',
  `Address` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Supplier physical address ',
  UNIQUE KEY `SupplierID` (`SupplierID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
DROP TABLE IF EXISTS `unit`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `unit` (
  `UnitID` int NOT NULL COMMENT 'Unique identifier for a unit ',
  `UnitName` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Name of measurement unit ',
  `Description` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'Explanation of unit ',
  PRIMARY KEY (`UnitID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;
